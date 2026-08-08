"""小红书关键词搜索爬虫（Playwright + API/DOM 双通道）。"""
from __future__ import annotations

import logging
import os
from typing import Any

from services.xhs import common as xc

log = logging.getLogger(__name__)

_NOTE_SELECTOR = 'a[href*="/explore/"], a[href*="/search_result/"], section.note-item'

_EXTRACT_JS = """
() => {
  const out = [];
  const seen = new Set();
  const push = (noteId, partial) => {
    if (!noteId || seen.has(noteId)) return;
    seen.add(noteId);
    out.push({
      note_id: noteId,
      url: partial.url || ('https://www.xiaohongshu.com/explore/' + noteId),
      title: (partial.title || '').slice(0, 120),
      author: (partial.author || '').slice(0, 80),
      likes_text: partial.likes_text || null,
      snippet: (partial.snippet || '').slice(0, 300),
    });
  };
  const parseCard = (card, noteId, href) => {
    const text = (card.innerText || '').slice(0, 900);
    const lines = text.split(/\\n+/).map(s => s.trim()).filter(Boolean);
    let title = lines.find(l => l.length >= 2 && !/^[\\d.]+\\s*[万亿wW]?$/.test(l)) || '';
    let author = '';
    let likes = null;
    for (const line of lines) {
      if (/^@/.test(line)) { author = line.replace(/^@/, '').trim(); continue; }
      if (/赞|点赞|like/i.test(line)) {
        const lm = line.match(/([\\d.]+\\s*[万亿wW]?)/);
        if (lm) likes = lm[1];
      }
    }
    push(noteId, {
      url: (href || '').split('?')[0],
      title, author, likes_text: likes, snippet: text.slice(0, 300),
    });
  };
  document.querySelectorAll('a[href*="/explore/"], a[href*="/discovery/item/"]').forEach(a => {
    let href = a.href || a.getAttribute('href') || '';
    if (!href || href.includes('javascript')) return;
    let noteId = (href.match(/\\/explore\\/([a-f0-9]{24})/i) || [])[1]
      || (href.match(/\\/discovery\\/item\\/([a-f0-9]{24})/i) || [])[1]
      || (href.match(/\\/([a-f0-9]{24})(?:\\?|$)/i) || [])[1];
    if (!noteId) return;
    let card = a.closest('section, div.note-item, div[class*="note"], li') || a.parentElement || a;
    parseCard(card, noteId, href);
  });
  document.querySelectorAll('section.note-item, [class*="note-item"]').forEach(card => {
    const a = card.querySelector('a[href*="/explore/"], a[href*="/discovery/item/"]');
    if (!a) return;
    const href = a.href || a.getAttribute('href') || '';
    let noteId = (href.match(/\\/explore\\/([a-f0-9]{24})/i) || [])[1]
      || (href.match(/\\/([a-f0-9]{24})/i) || [])[1];
    if (!noteId) return;
    parseCard(card, noteId, href);
  });
  return out.slice(0, 120);
}
"""


def _parse_api_payload(data: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def _from_note(note: dict) -> None:
        nid = str(note.get("id") or note.get("note_id") or note.get("noteId") or "").strip()
        if not nid:
            return
        user = note.get("user") or note.get("author") or {}
        if not isinstance(user, dict):
            user = {}
        interact = note.get("interact_info") or note.get("interactInfo") or note.get("liked_count") or {}
        likes = ""
        if isinstance(interact, dict):
            likes = str(interact.get("liked_count") or interact.get("likedCount") or "")
        elif interact:
            likes = str(interact)
        rows.append(
            {
                "note_id": nid,
                "url": f"https://www.xiaohongshu.com/explore/{nid}",
                "title": str(note.get("title") or note.get("display_title") or note.get("desc") or "")[:120],
                "author": str(user.get("nickname") or user.get("name") or "")[:80],
                "likes_text": likes,
                "snippet": str(note.get("desc") or note.get("title") or "")[:300],
            }
        )

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if any(k in obj for k in ("note_id", "noteId", "interact_info", "interactInfo")):
                _from_note(obj)
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(data)
    return rows


def _merge_items(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for raw in group:
            nid = str(raw.get("note_id") or "").strip()
            if not nid or nid in seen:
                continue
            seen.add(nid)
            out.append(raw)
    return out


def _poll_collect(page, api_items: list[dict[str, Any]], *, max_sec: int) -> list[dict[str, Any]]:
    import time

    deadline = time.time() + max(10, int(max_sec))
    best: list[dict[str, Any]] = []
    round_n = 0
    while time.time() < deadline:
        round_n += 1
        try:
            page.mouse.wheel(0, 1400 + round_n * 300)
        except Exception:
            pass
        page.wait_for_timeout(1600)
        try:
            dom = page.evaluate(_EXTRACT_JS) or []
        except Exception:
            dom = []
        merged = _merge_items(api_items, dom)
        if len(merged) > len(best):
            best = merged
        if len(merged) >= 10 or (len(merged) >= 3 and round_n >= 5):
            break
    return best


def _fetch_raw(search_url: str, *, storage_state: str, cookie_file: str) -> tuple[list[dict[str, Any]], bool]:
    from playwright.sync_api import sync_playwright

    headed_modes = [True]
    if xc.playwright_headless() and os.environ.get("XHS_HEADED_ON_CAPTCHA", "1") not in ("0", "false"):
        headed_modes.append(False)
    elif not xc.playwright_headless():
        headed_modes = [False]

    captcha_seen = False
    last_items: list[dict[str, Any]] = []
    api_items: list[dict[str, Any]] = []
    debug_shot = xc.debug_dir() / "search_last.png"

    for headless in headed_modes:
        with sync_playwright() as p:
            browser = xc.launch_browser(p, headless=headless)
            try:
                ctx_kw = xc.browser_context_kwargs(storage_state=storage_state, cookie_file=cookie_file)
                ctx_kw.setdefault("extra_http_headers", {})["Referer"] = "https://www.xiaohongshu.com/"
                context = browser.new_context(**ctx_kw)
                xc.apply_stealth(context)
                page = context.new_page()
                api_items = []

                def _on_response(response) -> None:
                    url = response.url or ""
                    if not any(x in url for x in ("search", "notes", "feed", "edith")):
                        return
                    try:
                        if response.status != 200:
                            return
                        parsed = _parse_api_payload(response.json())
                        if parsed:
                            api_items.extend(parsed)
                    except Exception:
                        pass

                page.on("response", _on_response)
                page.goto(search_url, wait_until="domcontentloaded", timeout=xc.nav_timeout_ms())
                if not headless:
                    try:
                        page.bring_to_front()
                    except Exception:
                        pass

                if xc.page_has_captcha(page):
                    captcha_seen = True
                    if headless and len(headed_modes) > 1:
                        continue
                    xc.wait_for_content(page, max_sec=xc.captcha_wait_sec(), selector=_NOTE_SELECTOR)

                last_items = _poll_collect(page, api_items, max_sec=xc.collect_wait_sec())
                if not last_items and xc.page_has_captcha(page):
                    captcha_seen = True
                    xc.wait_for_content(page, max_sec=min(45, xc.captcha_wait_sec()), selector=_NOTE_SELECTOR)
                    last_items = _poll_collect(page, api_items, max_sec=xc.collect_wait_sec())
                try:
                    page.screenshot(path=str(debug_shot), full_page=False)
                except Exception:
                    pass
            finally:
                browser.close()
        if last_items or not captcha_seen:
            break
    return last_items, captcha_seen


def search_xhs(
    keyword: str,
    *,
    min_likes: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    kw = (keyword or "").strip()
    if not kw:
        return {"ok": False, "error": "empty_keyword", "platform": "xiaohongshu"}
    if not xc.xhs_enabled():
        return {"ok": False, "error": "xhs_crawler_disabled", "platform": "xiaohongshu"}
    if not xc.playwright_installed():
        return {
            "ok": False,
            "error": "playwright_not_installed",
            "platform": "xiaohongshu",
            "hint": "pip install playwright && python -m playwright install chromium",
        }

    st = xc.resolve_storage_state()
    cf = xc.resolve_cookie_file()
    if not st and not cf:
        return {
            "ok": False,
            "error": "xhs_cookie_missing",
            "platform": "xiaohongshu",
            "hint": (
                "请配置 XHS_STORAGE_STATE 或 XHS_COOKIE_FILE。"
                "运行 scripts/export_xhs_storage.py 导出登录态"
            ),
        }

    search_url = xc.build_search_url(kw)
    lim = max(1, min(int(limit or 20), 30))
    debug_shot = xc.debug_dir() / "search_last.png"

    try:
        raw_items, captcha_seen = _fetch_raw(search_url, storage_state=st, cookie_file=cf)
    except Exception as exc:
        err = str(exc)[:500]
        if "login" in err.lower() or "登录" in err:
            return {"ok": False, "error": "xhs_login_required", "platform": "xiaohongshu", "detail": err}
        return {"ok": False, "error": "search_failed", "platform": "xiaohongshu", "detail": err}

    if not raw_items:
        base = {
            "platform": "xiaohongshu",
            "scanned": 0,
            "debug_screenshot": str(debug_shot) if debug_shot.is_file() else None,
        }
        if captcha_seen:
            return {
                "ok": False,
                "error": "xhs_captcha_required",
                "platform": "xiaohongshu",
                "hint": "出现验证。设置 XHS_PLAYWRIGHT_HEADLESS=0 后重试。",
                **base,
            }
        return {"ok": False, "error": "xhs_no_results", "platform": "xiaohongshu", **base}

    items: list[dict[str, Any]] = []
    for raw in raw_items:
        nid = str(raw.get("note_id") or "").strip()
        url = str(raw.get("url") or f"https://www.xiaohongshu.com/explore/{nid}").split("?")[0]
        likes = xc.parse_count_text(str(raw.get("likes_text") or ""))
        if min_likes and likes is not None and likes < min_likes:
            continue
        items.append(
            {
                "platform": "xiaohongshu",
                "video_id": nid,
                "note_id": nid,
                "url": url,
                "title": str(raw.get("title") or "").strip() or f"小红书笔记 {nid[:8]}",
                "author": str(raw.get("author") or "").strip(),
                "likes": likes,
                "comments": None,
                "followers": None,
                "snippet": str(raw.get("snippet") or "").strip(),
                "source": "xhs_crawler",
            }
        )

    items.sort(key=lambda x: (x.get("likes") is None, -(x.get("likes") or 0)))
    items = items[:lim]
    return {
        "ok": True,
        "platform": "xiaohongshu",
        "keyword": kw,
        "search_url": search_url,
        "scanned": len(raw_items),
        "count": len(items),
        "items": items,
        "source": "live_crawler",
    }
