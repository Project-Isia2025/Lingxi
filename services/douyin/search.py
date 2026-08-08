"""抖音关键词搜索爬虫（Playwright + API/DOM 双通道）。"""
from __future__ import annotations

import logging
import os
from typing import Any

from services.douyin import common as dc

log = logging.getLogger(__name__)

_VIDEO_SELECTOR = 'a[href*="/video/"]'

_EXTRACT_JS = """
() => {
  const out = [];
  const seen = new Set();
  const push = (vid, partial) => {
    if (!vid || seen.has(vid)) return;
    seen.add(vid);
    out.push({
      video_id: vid,
      url: partial.url || ('https://www.douyin.com/video/' + vid),
      title: (partial.title || '').slice(0, 120),
      author: (partial.author || '').slice(0, 80),
      likes_text: partial.likes_text || null,
      followers_text: partial.followers_text || null,
      snippet: (partial.snippet || '').slice(0, 300),
    });
  };
  const parseCard = (card, vid, href) => {
    const text = (card.innerText || '').slice(0, 900);
    const lines = text.split(/\\n+/).map(s => s.trim()).filter(Boolean);
    let title = lines.find(l => l.length >= 2 && !/^[\\d.]+\\s*[万亿wW]?$/.test(l)) || '';
    let author = '';
    let likes = null;
    let followers = null;
    for (const line of lines) {
      if (/^@/.test(line)) { author = line.replace(/^@/, '').trim(); continue; }
      if (/粉丝/.test(line)) {
        const fm = line.match(/([\\d.]+\\s*[万亿wW]?)/);
        if (fm) followers = fm[1];
      }
      if (/赞|点赞|like/i.test(line)) {
        const lm = line.match(/([\\d.]+\\s*[万亿wW]?)/);
        if (lm) likes = lm[1];
      }
    }
    push(vid, {
      url: (href || '').split('?')[0] || ('https://www.douyin.com/video/' + vid),
      title, author, likes_text: likes, followers_text: followers, snippet: text.slice(0, 300),
    });
  };
  document.querySelectorAll('a[href*="/video/"], a[href*="modal_id="]').forEach(a => {
    let href = a.href || a.getAttribute('href') || '';
    if (!href || href.includes('javascript')) return;
    let vid = (href.match(/\\/video\\/(\\d+)/) || [])[1] || (href.match(/modal_id=(\\d+)/) || [])[1];
    if (!vid) return;
    let card = a.closest('li, section, div[class*="card"], div[class*="item"]') || a.parentElement || a;
    parseCard(card, vid, href);
  });
  document.querySelectorAll('[data-e2e="search-card-item"], [data-e2e="search-video-item"]').forEach(card => {
    const a = card.querySelector('a[href*="/video/"], a[href*="modal_id="]');
    if (!a) return;
    const href = a.href || a.getAttribute('href') || '';
    let vid = (href.match(/\\/video\\/(\\d+)/) || [])[1] || (href.match(/modal_id=(\\d+)/) || [])[1];
    if (!vid) return;
    parseCard(card, vid, href);
  });
  const html = document.documentElement ? document.documentElement.innerHTML : '';
  for (const m of html.matchAll(/\\/video\\/(\\d{15,22})/g)) push(m[1], { title: '' });
  return out.slice(0, 120);
}
"""


def _parse_api_payload(data: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def _from_info(info: dict) -> None:
        vid = str(info.get("aweme_id") or info.get("awemeId") or info.get("id") or "").strip()
        if not vid or vid == "0":
            return
        author = info.get("author") or info.get("author_info") or {}
        stats = info.get("statistics") or info.get("stats") or {}
        if not isinstance(author, dict):
            author = {}
        if not isinstance(stats, dict):
            stats = {}
        rows.append(
            {
                "video_id": vid,
                "url": f"https://www.douyin.com/video/{vid}",
                "title": str(info.get("desc") or info.get("title") or "")[:120],
                "author": str(author.get("nickname") or author.get("unique_id") or "")[:80],
                "likes_text": str(stats.get("digg_count") or stats.get("diggCount") or ""),
                "play_count_text": str(stats.get("play_count") or stats.get("playCount") or stats.get("view_count") or ""),
                "followers_text": str(author.get("follower_count") or author.get("followerCount") or ""),
                "snippet": str(info.get("desc") or "")[:300],
            }
        )

    if isinstance(data, dict):
        for key in ("data", "aweme_list", "item_list"):
            block = data.get(key)
            if isinstance(block, list):
                for row in block:
                    if not isinstance(row, dict):
                        continue
                    info = row.get("aweme_info") or row.get("aweme") or row
                    if isinstance(info, dict):
                        _from_info(info)
    return rows


def _merge_items(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for raw in group:
            vid = str(raw.get("video_id") or "").strip()
            if not vid or vid in seen:
                continue
            seen.add(vid)
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
    if dc.playwright_headless() and os.environ.get("DOUYIN_HEADED_ON_CAPTCHA", "1") not in ("0", "false"):
        headed_modes.append(False)
    elif not dc.playwright_headless():
        headed_modes = [False]

    captcha_seen = False
    last_items: list[dict[str, Any]] = []
    api_items: list[dict[str, Any]] = []
    debug_shot = dc.debug_dir() / "search_last.png"

    for headless in headed_modes:
        with sync_playwright() as p:
            browser = dc.launch_browser(p, headless=headless)
            try:
                ctx_kw = dc.browser_context_kwargs(storage_state=storage_state, cookie_file=cookie_file)
                ctx_kw.setdefault("extra_http_headers", {})["Referer"] = "https://www.douyin.com/"
                context = browser.new_context(**ctx_kw)
                dc.apply_stealth(context)
                page = context.new_page()
                api_items = []

                def _on_response(response) -> None:
                    url = response.url or ""
                    if not any(x in url for x in ("search", "aweme/v1/web")):
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
                page.goto(search_url, wait_until="domcontentloaded", timeout=dc.nav_timeout_ms())
                if not headless:
                    try:
                        page.bring_to_front()
                    except Exception:
                        pass

                if dc.page_has_captcha(page):
                    captcha_seen = True
                    if headless and len(headed_modes) > 1:
                        continue
                    dc.wait_for_content(page, max_sec=dc.captcha_wait_sec(), selector=_VIDEO_SELECTOR)

                last_items = _poll_collect(page, api_items, max_sec=dc.collect_wait_sec())
                if not last_items and dc.page_has_captcha(page):
                    captcha_seen = True
                    dc.wait_for_content(page, max_sec=min(45, dc.captcha_wait_sec()), selector=_VIDEO_SELECTOR)
                    last_items = _poll_collect(page, api_items, max_sec=dc.collect_wait_sec())
                try:
                    page.screenshot(path=str(debug_shot), full_page=False)
                except Exception:
                    pass
            finally:
                browser.close()
        if last_items or not captcha_seen:
            break
    return last_items, captcha_seen


def search_douyin(
    keyword: str,
    *,
    min_likes: int = 0,
    min_followers: int = 0,
    min_like_rate: float | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    kw = (keyword or "").strip()
    if not kw:
        return {"ok": False, "error": "empty_keyword", "platform": "douyin"}
    if not dc.douyin_enabled():
        return {"ok": False, "error": "douyin_crawler_disabled", "platform": "douyin"}
    if not dc.playwright_installed():
        return {
            "ok": False,
            "error": "playwright_not_installed",
            "platform": "douyin",
            "hint": "pip install playwright && python -m playwright install chromium",
        }

    st = dc.resolve_storage_state()
    cf = dc.resolve_cookie_file()
    if not st and not cf:
        return {
            "ok": False,
            "error": "douyin_cookie_missing",
            "platform": "douyin",
            "hint": (
                "请配置 DOUYIN_STORAGE_STATE 或 DOUYIN_COOKIE_FILE。"
                "运行 scripts/export_douyin_storage.py 导出登录态到 data/state/douyin_pc_storage.json"
            ),
        }

    search_url = dc.build_search_url(kw)
    lim = max(1, min(int(limit or 20), 30))
    debug_shot = dc.debug_dir() / "search_last.png"

    try:
        raw_items, captcha_seen = _fetch_raw(search_url, storage_state=st, cookie_file=cf)
    except Exception as exc:
        err = str(exc)[:500]
        if "login" in err.lower() or "登录" in err:
            return {"ok": False, "error": "douyin_login_required", "platform": "douyin", "detail": err}
        return {"ok": False, "error": "search_failed", "platform": "douyin", "detail": err}

    if not raw_items:
        base = {"platform": "douyin", "scanned": 0, "debug_screenshot": str(debug_shot) if debug_shot.is_file() else None}
        if captcha_seen:
            return {
                "ok": False,
                "error": "douyin_captcha_required",
                "platform": "douyin",
                "hint": "出现滑块验证。设置 DOUYIN_PLAYWRIGHT_HEADLESS=0 后重试，手动完成验证。",
                **base,
            }
        return {"ok": False, "error": "douyin_no_results", "platform": "douyin", **base}

    items: list[dict[str, Any]] = []
    for raw in raw_items:
        vid = str(raw.get("video_id") or "").strip()
        url = str(raw.get("url") or f"https://www.douyin.com/video/{vid}").split("?")[0]
        likes = dc.parse_count_text(str(raw.get("likes_text") or ""))
        views = dc.parse_count_text(str(raw.get("play_count_text") or ""))
        followers = dc.parse_count_text(str(raw.get("followers_text") or ""))
        if min_likes and likes is not None and likes < min_likes:
            continue
        if min_followers and followers is not None and followers < min_followers:
            continue
        items.append(
            {
                "platform": "douyin",
                "video_id": vid,
                "url": url,
                "title": str(raw.get("title") or "").strip() or f"抖音视频 {vid}",
                "author": str(raw.get("author") or "").strip(),
                "likes": likes,
                "views": views,
                "comments": None,
                "followers": followers,
                "snippet": str(raw.get("snippet") or "").strip(),
                "source": "douyin_crawler",
            }
        )

    from services.perception_engagement import filter_by_like_rate

    passed, skipped = filter_by_like_rate(items, min_rate=min_like_rate, strict=False)
    items = passed
    items.sort(key=lambda x: (x.get("likes") is None, -(x.get("likes") or 0)))
    items = items[:lim]
    return {
        "ok": True,
        "platform": "douyin",
        "keyword": kw,
        "search_url": search_url,
        "scanned": len(raw_items),
        "count": len(items),
        "items": items,
        "source": "live_crawler",
        "like_rate_filtered": {"passed": len(passed), "skipped": len(skipped)},
    }
