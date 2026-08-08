"""抖音热榜抓取（Playwright + 样本库回退）。"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import bootstrap
from services.douyin import common as dc

log = logging.getLogger(__name__)

_HOT_URL = "https://www.douyin.com/hot"

_EXTRACT_HOT_JS = """
() => {
  const out = [];
  const seen = new Set();
  const push = (title, extra) => {
    const t = (title || '').trim();
    if (!t || t.length < 2 || seen.has(t)) return;
    seen.add(t);
    out.push({ title: t.slice(0, 120), heat_text: extra.heat || '', rank: out.length + 1 });
  };
  document.querySelectorAll('[data-e2e="hot-item"], li, a').forEach(el => {
    const text = (el.innerText || '').trim();
    if (!text || text.length > 200) return;
    const lines = text.split(/\\n+/).map(s => s.trim()).filter(Boolean);
    if (lines.length >= 1 && lines[0].length >= 2) {
      const heat = lines.find(l => /万|热|↑|°/.test(l)) || '';
      if (/^\\d+$/.test(lines[0]) && lines[1]) push(lines[1], { heat: lines[0] });
      else if (lines[0].length >= 2 && !/^\\d+$/.test(lines[0])) push(lines[0], { heat });
    }
  });
  return out.slice(0, 50);
}
"""


def _curated_hotlist(*, limit: int = 20) -> list[dict[str, Any]]:
    path = bootstrap.project_root() / "data" / "douyin_hotlist.json"
    items: list[dict[str, Any]] = []
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                items = [x for x in raw if isinstance(x, dict)]
        except Exception:
            items = []
    if not items:
        items = [
            {"rank": 1, "title": "春季护肤避坑", "heat_text": "856万", "keyword": "护肤"},
            {"rank": 2, "title": "面膜怎么选", "heat_text": "620万", "keyword": "面膜"},
            {"rank": 3, "title": "成分党测评", "heat_text": "410万", "keyword": "成分"},
            {"rank": 4, "title": "15秒口播模板", "heat_text": "380万", "keyword": "口播"},
            {"rank": 5, "title": "爆款BGM合集", "heat_text": "290万", "keyword": "BGM"},
        ]
    for i, item in enumerate(items[:limit]):
        item.setdefault("rank", i + 1)
        item.setdefault("source", "curated")
        if not item.get("keyword"):
            item["keyword"] = str(item.get("title") or "")[:12]
    return items[:limit]


def fetch_douyin_hotlist(*, limit: int = 20) -> dict[str, Any]:
    lim = max(1, min(int(limit or 20), 50))
    if not dc.douyin_enabled() or not dc.playwright_installed():
        items = _curated_hotlist(limit=lim)
        return {"ok": True, "source": "curated", "count": len(items), "items": items}

    st = dc.resolve_storage_state()
    cf = dc.resolve_cookie_file()
    if not st and not cf:
        items = _curated_hotlist(limit=lim)
        return {"ok": True, "source": "curated", "count": len(items), "items": items, "hint": "douyin_cookie_missing"}

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = dc.launch_browser(p, headless=dc.playwright_headless())
            try:
                ctx_kw = dc.browser_context_kwargs(storage_state=st, cookie_file=cf)
                context = browser.new_context(**ctx_kw)
                dc.apply_stealth(context)
                page = context.new_page()
                page.goto(_HOT_URL, wait_until="domcontentloaded", timeout=dc.nav_timeout_ms())
                page.wait_for_timeout(2500)
                raw = page.evaluate(_EXTRACT_HOT_JS) or []
            finally:
                browser.close()
        items = []
        for i, row in enumerate(raw[:lim]):
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "").strip()
            if not title:
                continue
            kw = re.sub(r"[#【】]", "", title).strip()[:16]
            items.append({
                "rank": i + 1,
                "title": title,
                "heat_text": str(row.get("heat_text") or ""),
                "keyword": kw or title[:8],
                "source": "live_crawler",
            })
        if items:
            return {"ok": True, "source": "live_crawler", "count": len(items), "items": items}
    except Exception as exc:
        log.warning("douyin hotlist crawl failed: %s", exc)

    items = _curated_hotlist(limit=lim)
    return {"ok": True, "source": "curated", "count": len(items), "items": items}
