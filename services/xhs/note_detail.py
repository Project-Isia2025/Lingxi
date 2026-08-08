"""小红书笔记详情抓取（正文/标签/互动/OCR）。"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from services.xhs import common as xc

log = logging.getLogger(__name__)

_NOTE_ID_RE = re.compile(r"(?:explore|discovery/item)/([a-f0-9]{24})", re.I)

_EXTRACT_NOTE_JS = """
() => {
  const text = (document.body?.innerText || '').slice(0, 8000);
  const titleEl = document.querySelector('#detail-title, .title, [class*="note-title"], h1');
  const descEl = document.querySelector('#detail-desc, .desc, [class*="note-text"], [class*="content"]');
  const tags = [];
  document.querySelectorAll('a[href*="/search_result"], .tag, [class*="tag"]').forEach(el => {
    const t = (el.innerText || '').trim();
    if (t && t.length <= 30) tags.push(t.replace(/^#/, ''));
  });
  let likes = null;
  for (const line of text.split(/\\n+/)) {
    if (/赞|点赞/.test(line)) {
      const m = line.match(/([\\d.]+\\s*[万亿wW]?)/);
      if (m) likes = m[1];
    }
  }
  const imgs = [];
  document.querySelectorAll('img').forEach(img => {
    const src = img.currentSrc || img.src || img.getAttribute('data-src') || '';
    if (src && src.startsWith('http') && !src.includes('avatar')) imgs.push(src.split('?')[0]);
  });
  const videos = [];
  document.querySelectorAll('video source, video').forEach(el => {
    const src = el.src || el.getAttribute('src') || '';
    if (src && src.startsWith('http')) videos.push(src.split('?')[0]);
  });
  return {
    title: (titleEl?.innerText || '').trim().slice(0, 200),
    body: (descEl?.innerText || text).trim().slice(0, 3000),
    tags: [...new Set(tags)].slice(0, 15),
    likes_text: likes,
    page_excerpt: text.slice(0, 500),
    image_urls: [...new Set(imgs)].slice(0, 8),
    video_urls: [...new Set(videos)].slice(0, 3),
  };
}
"""


def parse_note_id(url_or_id: str) -> str:
    s = (url_or_id or "").strip()
    if re.fullmatch(r"[a-f0-9]{24}", s, re.I):
        return s
    m = _NOTE_ID_RE.search(s)
    return m.group(1) if m else ""


def build_note_url(note_id: str) -> str:
    return f"https://www.xiaohongshu.com/explore/{note_id}"


def _fetch_note_page(note_id: str) -> tuple[dict[str, Any], bool]:
    from playwright.sync_api import sync_playwright

    url = build_note_url(note_id)
    st = xc.resolve_storage_state()
    cf = xc.resolve_cookie_file()
    captcha = False
    data: dict[str, Any] = {}

    with sync_playwright() as p:
        browser = xc.launch_browser(p, headless=xc.playwright_headless())
        try:
            ctx_kw = xc.browser_context_kwargs(storage_state=st, cookie_file=cf)
            context = browser.new_context(**ctx_kw)
            xc.apply_stealth(context)
            page = context.new_page()

            api_payload: dict[str, Any] = {}

            def _on_response(response) -> None:
                u = response.url or ""
                if "note" not in u and "feed" not in u:
                    return
                try:
                    if response.status == 200:
                        api_payload.update(response.json() if response.headers.get("content-type", "").startswith("application/json") else {})
                except Exception:
                    pass

            page.on("response", _on_response)
            page.goto(url, wait_until="domcontentloaded", timeout=xc.nav_timeout_ms())
            if xc.page_has_captcha(page):
                captcha = True
            page.wait_for_timeout(2000)
            dom = page.evaluate(_EXTRACT_NOTE_JS) or {}
            data = _merge_note_data(note_id, dom, api_payload)
        finally:
            browser.close()
    return data, captcha


def _merge_note_data(note_id: str, dom: dict, api: Any) -> dict[str, Any]:
    title = str(dom.get("title") or "")
    body = str(dom.get("body") or "")
    tags = list(dom.get("tags") or [])
    likes_text = dom.get("likes_text")

    def _walk(obj: Any) -> None:
        nonlocal title, body, tags, likes_text
        if isinstance(obj, dict):
            if obj.get("desc") and len(str(obj["desc"])) > len(body):
                body = str(obj["desc"])[:3000]
            if obj.get("title") and not title:
                title = str(obj["title"])[:200]
            note = obj.get("note") or obj.get("note_detail") or obj.get("noteDetail")
            if isinstance(note, dict):
                if note.get("desc"):
                    body = str(note["desc"])[:3000]
                if note.get("title"):
                    title = str(note["title"])[:200]
                interact = note.get("interact_info") or note.get("interactInfo") or {}
                if isinstance(interact, dict) and interact.get("liked_count"):
                    likes_text = str(interact.get("liked_count"))
                tag_list = note.get("tag_list") or note.get("tagList") or []
                if isinstance(tag_list, list):
                    for t in tag_list:
                        if isinstance(t, dict) and t.get("name"):
                            tags.append(str(t["name"]))
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(api)
    likes = xc.parse_count_text(str(likes_text or ""))
    video_urls: list[str] = list(dom.get("video_urls") or [])

    def _collect_video(obj: Any) -> None:
        nonlocal video_urls
        if isinstance(obj, dict):
            for k in ("video_url", "videoUrl", "master_url", "masterUrl", "url"):
                v = obj.get(k)
                if isinstance(v, str) and v.startswith("http") and ("video" in v or v.endswith(".mp4")):
                    video_urls.append(v.split("?")[0])
            for v in obj.values():
                _collect_video(v)
        elif isinstance(obj, list):
            for item in obj:
                _collect_video(item)

    _collect_video(api)
    return {
        "note_id": note_id,
        "url": build_note_url(note_id),
        "title": title or f"笔记 {note_id[:8]}",
        "body": body,
        "tags": list(dict.fromkeys(tags))[:15],
        "likes": likes,
        "likes_text": likes_text,
        "image_urls": list(dom.get("image_urls") or [])[:8],
        "video_urls": list(dict.fromkeys(video_urls))[:3],
    }


def _apply_note_ocr(data: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get("XHS_OCR_ENABLED", "1").strip().lower() in ("0", "false", "no"):
        return {"ok": False, "skipped": True}
    urls = data.get("image_urls") or []
    if not urls:
        return {"ok": False, "error": "no_images"}
    try:
        from services.ocr import ocr_images

        limit = int(os.environ.get("XHS_OCR_IMAGE_LIMIT", "3") or 3)
        ocr_out = ocr_images(urls, limit=limit)
        if ocr_out.get("merged_text"):
            data["ocr_text"] = ocr_out["merged_text"]
            if len(str(data.get("body") or "")) < 80:
                data["body"] = (str(data.get("body") or "") + "\n" + ocr_out["merged_text"]).strip()
            data["ocr_meta"] = {
                "image_count": ocr_out.get("image_count"),
                "success_count": ocr_out.get("success_count"),
            }
            try:
                from services.asr_memory import ingest_ocr_text

                ocr_out["memory"] = ingest_ocr_text(
                    text=ocr_out["merged_text"],
                    title=str(data.get("title") or ""),
                    platform="xiaohongshu",
                    note_id=str(data.get("note_id") or ""),
                    source_url=str(data.get("url") or ""),
                )
            except Exception as exc:
                ocr_out["memory_error"] = str(exc)[:200]
        return ocr_out
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _apply_note_asr(data: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get("XHS_ASR_ENABLED", os.environ.get("ASR_ENABLED", "1")).strip().lower() in ("0", "false", "no"):
        return {"ok": False, "skipped": True}
    urls = data.get("video_urls") or []
    if not urls:
        return {"ok": False, "error": "no_video"}
    try:
        from services.asr import transcribe_url

        out = transcribe_url(str(urls[0]))
        if out.get("ok") and out.get("text"):
            data["asr_text"] = out["text"]
            if len(str(data.get("body") or "")) < 120:
                data["body"] = (str(data.get("body") or "") + "\n" + out["text"]).strip()
            try:
                from services.asr_memory import ingest_asr_transcript

                out["memory"] = ingest_asr_transcript(
                    text=out["text"],
                    title=str(data.get("title") or ""),
                    platform="xiaohongshu",
                    note_id=str(data.get("note_id") or ""),
                    source_url=str(data.get("url") or ""),
                )
            except Exception as exc:
                out["memory_error"] = str(exc)[:200]
        return out
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def fetch_note_detail(url_or_id: str) -> dict[str, Any]:
    note_id = parse_note_id(url_or_id)
    if not note_id:
        return {"ok": False, "error": "invalid_note_id", "input": url_or_id}
    if not xc.xhs_enabled():
        return {"ok": False, "error": "xhs_crawler_disabled"}
    if not xc.playwright_installed():
        return {"ok": False, "error": "playwright_not_installed"}
    st = xc.resolve_storage_state()
    cf = xc.resolve_cookie_file()
    if not st and not cf:
        return {"ok": False, "error": "xhs_cookie_missing"}

    try:
        data, captcha = _fetch_note_page(note_id)
    except Exception as exc:
        return {"ok": False, "error": "fetch_failed", "detail": str(exc)[:300]}

    if not data.get("body") and not data.get("title"):
        if captcha:
            return {"ok": False, "error": "xhs_captcha_required", "note_id": note_id}
        return {"ok": False, "error": "empty_note_content", "note_id": note_id}

    ocr_result = _apply_note_ocr(data)
    asr_result = _apply_note_asr(data)
    return {
        "ok": True,
        "platform": "xiaohongshu",
        "source": "note_detail_crawler",
        "ocr": ocr_result,
        "asr": asr_result,
        **data,
    }


def enrich_competitors(competitors: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    """为竞品列表 Top N 补充正文深度信息。"""
    out: list[dict[str, Any]] = []
    enriched = 0
    for item in competitors:
        row = dict(item)
        if enriched < limit and str(row.get("platform") or "").lower() in ("xiaohongshu", "xhs"):
            nid = str(row.get("note_id") or row.get("video_id") or parse_note_id(str(row.get("url") or "")))
            if nid:
                detail = fetch_note_detail(nid)
                if detail.get("ok"):
                    row["body"] = detail.get("body") or row.get("snippet") or ""
                    row["tags"] = detail.get("tags") or []
                    row["title"] = detail.get("title") or row.get("title")
                    row["likes"] = detail.get("likes") if detail.get("likes") is not None else row.get("likes")
                    row["ocr_text"] = detail.get("ocr_text") or ""
                    row["asr_text"] = detail.get("asr_text") or ""
                    row["image_urls"] = detail.get("image_urls") or []
                    row["detail_fetched"] = True
                    enriched += 1
                    if row.get("asr_text"):
                        try:
                            from services.asr_memory import ingest_competitor_asr

                            ingest_competitor_asr(row)
                        except Exception:
                            pass
                else:
                    row["detail_error"] = detail.get("error")
        out.append(row)
    return out
