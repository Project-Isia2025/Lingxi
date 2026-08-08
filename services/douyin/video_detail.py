"""抖音视频详情页：补全播放量/点赞/评论，用于点赞率过滤。"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from services.douyin import common as dc

log = logging.getLogger(__name__)

_VIDEO_ID_RE = re.compile(r"/video/(\d{15,22})")

_EXTRACT_DETAIL_JS = """
() => {
  const text = (document.body?.innerText || '').slice(0, 6000);
  const lines = text.split(/\\n+/).map(s => s.trim()).filter(Boolean);
  let likes = null, views = null, comments = null, shares = null;
  for (const line of lines) {
    if (/赞|点赞/.test(line) && !likes) {
      const m = line.match(/([\\d.]+\\s*[万亿wW]?)/);
      if (m) likes = m[1];
    }
    if (/播放/.test(line) && !views) {
      const m = line.match(/([\\d.]+\\s*[万亿wW]?)/);
      if (m) views = m[1];
    }
    if (/评论/.test(line) && !comments) {
      const m = line.match(/([\\d.]+\\s*[万亿wW]?)/);
      if (m) comments = m[1];
    }
    if (/分享/.test(line) && !shares) {
      const m = line.match(/([\\d.]+\\s*[万亿wW]?)/);
      if (m) shares = m[1];
    }
  }
  const titleEl = document.querySelector('[data-e2e="video-desc"], h1, [class*="title"]');
  return {
    title: (titleEl?.innerText || '').trim().slice(0, 200),
    likes_text: likes,
    views_text: views,
    comments_text: comments,
    shares_text: shares,
    page_excerpt: text.slice(0, 400),
  };
}
"""


def detail_enrich_enabled() -> bool:
    return os.environ.get("DOUYIN_ENRICH_DETAIL", "1").strip().lower() not in ("0", "false", "no", "off")


def detail_enrich_limit() -> int:
    try:
        return max(1, min(int(os.environ.get("DOUYIN_ENRICH_LIMIT", "5")), 15))
    except ValueError:
        return 5


def parse_video_id(url_or_id: str) -> str:
    s = (url_or_id or "").strip()
    if re.fullmatch(r"\d{15,22}", s):
        return s
    m = _VIDEO_ID_RE.search(s)
    return m.group(1) if m else ""


def build_video_url(video_id: str) -> str:
    return f"https://www.douyin.com/video/{video_id}"


def _parse_detail_api(data: Any) -> dict[str, Any]:
    """从 aweme detail API 响应提取 statistics。"""
    info: dict[str, Any] | None = None
    if isinstance(data, dict):
        for key in ("aweme_detail", "aweme_info", "aweme"):
            block = data.get(key)
            if isinstance(block, dict):
                info = block
                break
        if info is None and data.get("statistics"):
            info = data
    if not info:
        return {}

    stats = info.get("statistics") or info.get("stats") or {}
    if not isinstance(stats, dict):
        stats = {}
    author = info.get("author") or {}
    if not isinstance(author, dict):
        author = {}

    return {
        "video_id": str(info.get("aweme_id") or info.get("awemeId") or info.get("id") or ""),
        "title": str(info.get("desc") or info.get("title") or "")[:200],
        "author": str(author.get("nickname") or "")[:80],
        "likes": dc.parse_count_text(str(stats.get("digg_count") or stats.get("diggCount") or "")),
        "views": dc.parse_count_text(
            str(stats.get("play_count") or stats.get("playCount") or stats.get("view_count") or "")
        ),
        "comments": dc.parse_count_text(str(stats.get("comment_count") or stats.get("commentCount") or "")),
        "shares": dc.parse_count_text(str(stats.get("share_count") or stats.get("shareCount") or "")),
        "detail_source": "api",
    }


def fetch_video_detail(url_or_id: str) -> dict[str, Any]:
    """抓取单条视频详情（播放量/点赞/评论）。"""
    vid = parse_video_id(url_or_id)
    if not vid:
        return {"ok": False, "error": "invalid_video_id", "platform": "douyin"}

    if not dc.douyin_enabled() or not dc.playwright_installed():
        return {"ok": False, "error": "douyin_crawler_unavailable", "video_id": vid, "platform": "douyin"}

    st = dc.resolve_storage_state()
    cf = dc.resolve_cookie_file()
    if not st and not cf:
        return {"ok": False, "error": "douyin_cookie_missing", "video_id": vid, "platform": "douyin"}

    url = build_video_url(vid)
    api_detail: dict[str, Any] = {}
    dom_detail: dict[str, Any] = {}
    captcha = False

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = dc.launch_browser(p, headless=dc.playwright_headless())
            try:
                ctx_kw = dc.browser_context_kwargs(storage_state=st, cookie_file=cf)
                context = browser.new_context(**ctx_kw)
                dc.apply_stealth(context)
                page = context.new_page()
                captured: list[dict[str, Any]] = []

                def _on_response(response) -> None:
                    req_url = response.url or ""
                    if not any(x in req_url for x in ("aweme/detail", "aweme/v1/web/aweme/detail", "/video/")):
                        if "aweme" not in req_url:
                            return
                    try:
                        if response.status != 200:
                            return
                        parsed = _parse_detail_api(response.json())
                        if parsed.get("views") is not None or parsed.get("likes") is not None:
                            captured.append(parsed)
                    except Exception:
                        pass

                page.on("response", _on_response)
                page.goto(url, wait_until="domcontentloaded", timeout=dc.nav_timeout_ms())
                page.wait_for_timeout(2200)
                if dc.page_has_captcha(page):
                    captcha = True
                if captured:
                    api_detail = captured[-1]
                try:
                    dom_detail = page.evaluate(_EXTRACT_DETAIL_JS) or {}
                except Exception:
                    dom_detail = {}
            finally:
                browser.close()
    except Exception as exc:
        return {"ok": False, "error": "detail_fetch_failed", "detail": str(exc)[:300], "video_id": vid}

    likes = api_detail.get("likes")
    views = api_detail.get("views")
    comments = api_detail.get("comments")
    if dom_detail:
        if likes is None:
            likes = dc.parse_count_text(str(dom_detail.get("likes_text") or ""))
        if views is None:
            views = dc.parse_count_text(str(dom_detail.get("views_text") or ""))
        if comments is None:
            comments = dc.parse_count_text(str(dom_detail.get("comments_text") or ""))

    if likes is None and views is None:
        return {
            "ok": False,
            "error": "douyin_captcha_required" if captcha else "detail_no_stats",
            "video_id": vid,
            "url": url,
            "platform": "douyin",
            "captcha": captcha,
        }

    from services.perception_engagement import compute_like_rate

    like_rate = compute_like_rate(likes=likes, views=views)
    return {
        "ok": True,
        "platform": "douyin",
        "video_id": vid,
        "url": url,
        "title": api_detail.get("title") or dom_detail.get("title") or "",
        "author": api_detail.get("author") or "",
        "likes": likes,
        "views": views,
        "comments": comments,
        "shares": api_detail.get("shares"),
        "like_rate": like_rate,
        "detail_fetched": True,
        "detail_source": api_detail.get("detail_source") or ("dom" if dom_detail else "unknown"),
        "views_from_detail": True,
    }


def enrich_competitors(competitors: list[dict[str, Any]], *, limit: int | None = None) -> list[dict[str, Any]]:
    """为 Top N 抖音竞品补详情页播放量/点赞率。"""
    lim = int(limit or detail_enrich_limit())
    out: list[dict[str, Any]] = []
    enriched = 0
    for item in competitors:
        row = dict(item)
        plat = str(row.get("platform") or "").lower()
        if enriched < lim and plat in ("douyin", "tiktok", ""):
            vid = parse_video_id(str(row.get("url") or row.get("video_id") or ""))
            if vid:
                detail = fetch_video_detail(vid)
                if detail.get("ok"):
                    if detail.get("likes") is not None:
                        row["likes"] = detail["likes"]
                    if detail.get("views") is not None:
                        row["views"] = detail["views"]
                        row["views_from_detail"] = True
                        row.pop("views_estimated", None)
                    if detail.get("comments") is not None:
                        row["comments"] = detail["comments"]
                    if detail.get("like_rate") is not None:
                        row["like_rate"] = detail["like_rate"]
                    if detail.get("title"):
                        row["title"] = detail["title"]
                    row["detail_fetched"] = True
                    row["detail_source"] = detail.get("detail_source")
                    enriched += 1
                else:
                    row["detail_error"] = detail.get("error")
        out.append(row)
    return out
