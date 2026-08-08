"""创作者中心：完播/CTR 回采与真实下架。"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from services.douyin import common as dc
from services.publish import common as pub
from services.publish.playwright_util import playwright_installed, playwright_sync_context
from services.publish.router import PLATFORM_CONFIGS


def creator_metrics_enabled() -> bool:
    return os.environ.get("CREATOR_METRICS_ENABLED", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _plat(platform: str) -> str:
    p = (platform or "douyin").strip().lower()
    return "xiaohongshu" if p == "xhs" else p


def _post_id_from_url(post_url: str) -> str:
    u = (post_url or "").strip()
    m = re.search(r"/video/(\d{15,22})", u)
    if m:
        return m.group(1)
    m = re.search(r"/(?:explore|discovery/item)/([a-f0-9]{24})", u, re.I)
    if m:
        return m.group(1)
    return ""


def parse_metrics_from_text(text: str) -> dict[str, Any]:
    """从创作者中心页面文本解析完播率/CTR/播放量。"""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    completion_rate = None
    ctr = None
    views = None
    likes = None

    for line in lines:
        low = line.lower()
        if completion_rate is None and any(k in line for k in ("完播", "5s完播", "3s完播", "播放完成")):
            m = re.search(r"([\d.]+)\s*%", line)
            if m:
                completion_rate = round(float(m.group(1)) / 100.0, 4)
        if ctr is None and any(k in low for k in ("ctr", "点击率", "点击/展示")):
            m = re.search(r"([\d.]+)\s*%", line)
            if m:
                ctr = round(float(m.group(1)) / 100.0, 4)
        if views is None and "播放" in line:
            m = re.search(r"([\d.]+\s*[万亿wW]?)", line)
            if m:
                views = dc.parse_count_text(m.group(1))
        if likes is None and any(k in line for k in ("点赞", "赞")):
            m = re.search(r"([\d.]+\s*[万亿wW]?)", line)
            if m:
                likes = dc.parse_count_text(m.group(1))

    return {
        "completion_rate": completion_rate,
        "ctr": ctr,
        "views": views,
        "likes": likes,
    }


def _sample_metrics(*, platform: str, post_url: str) -> dict[str, Any]:
    path = pub.project_root() / "data" / "sample_post_metrics.json"
    pool: list[dict[str, Any]] = []
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                pool = [x for x in raw if isinstance(x, dict)]
        except Exception:
            pool = []
    if not pool:
        pool = [
            {"completion_rate": 0.38, "ctr": 0.012, "views": 12000, "likes": 860},
            {"completion_rate": 0.22, "ctr": 0.006, "views": 8000, "likes": 420},
        ]
    pid = _post_id_from_url(post_url)
    idx = sum(ord(c) for c in (pid or post_url)) % len(pool)
    row = dict(pool[idx])
    return {
        "ok": True,
        "platform": _plat(platform),
        "post_url": post_url,
        "completion_rate": row.get("completion_rate"),
        "ctr": row.get("ctr"),
        "views": row.get("views"),
        "likes": row.get("likes"),
        "source": "sample",
    }


_EXTRACT_METRICS_JS = """
(postId) => {
  const text = (document.body?.innerText || '').slice(0, 12000);
  const lines = text.split(/\\n+/).map(s => s.trim()).filter(Boolean);
  let completion = null, ctr = null, views = null, likes = null;
  const hasPost = !postId || text.includes(postId);
  for (const line of lines) {
    if (/完播|5s完播|3s完播|播放完成/.test(line)) {
      const m = line.match(/([\\d.]+)\\s*%/);
      if (m) completion = parseFloat(m[1]) / 100;
    }
    if (/点击率|CTR/i.test(line)) {
      const m = line.match(/([\\d.]+)\\s*%/);
      if (m) ctr = parseFloat(m[1]) / 100;
    }
    if (/播放/.test(line) && !views) {
      const m = line.match(/([\\d.]+\\s*[万亿wW]?)/);
      if (m) views = m[1];
    }
    if (/点赞|赞/.test(line) && !likes) {
      const m = line.match(/([\\d.]+\\s*[万亿wW]?)/);
      if (m) likes = m[1];
    }
  }
  return {
    has_post_hint: hasPost,
    completion_rate: completion,
    ctr,
    views_text: views,
    likes_text: likes,
    page_excerpt: text.slice(0, 400),
  };
}
"""


def fetch_creator_post_metrics(
    *,
    platform: str,
    post_url: str,
    account_id: str = "default",
) -> dict[str, Any]:
    """从创作者中心作品管理页回采完播率/CTR。"""
    plat = _plat(platform)
    post_url = (post_url or "").strip()
    if not post_url:
        return {"ok": False, "error": "empty_post_url", "platform": plat}

    if not creator_metrics_enabled():
        return _sample_metrics(platform=plat, post_url=post_url)

    storage = pub.resolve_storage(plat, account_id=account_id)
    if not storage or not Path(storage).is_file():
        out = _sample_metrics(platform=plat, post_url=post_url)
        out["hint"] = "creator_storage_missing"
        return out

    if not playwright_installed():
        out = _sample_metrics(platform=plat, post_url=post_url)
        out["hint"] = "playwright_not_installed"
        return out

    cfg_fn = PLATFORM_CONFIGS.get(plat)
    if not cfg_fn:
        return {"ok": False, "error": "unsupported_platform", "platform": plat}

    cfg = cfg_fn()
    manage_url = cfg.manage_url
    post_id = _post_id_from_url(post_url)
    headless = pub.env_truthy(cfg.headless_env, "1")

    try:
        with playwright_sync_context() as p:
            launch_kw: dict[str, Any] = {"headless": headless}
            channel = (os.environ.get("PUBLISH_PLAYWRIGHT_CHANNEL") or "").strip()
            if channel:
                launch_kw["channel"] = channel
            browser = p.chromium.launch(**launch_kw)
            try:
                context = browser.new_context(
                    storage_state=str(Path(storage).resolve()),
                    locale="zh-CN",
                    viewport={"width": 1440, "height": 900},
                    user_agent=pub.DEFAULT_UA,
                )
                page = context.new_page()
                target = post_url if post_url.startswith("http") else manage_url
                page.goto(target, wait_until="domcontentloaded", timeout=120_000)
                page.wait_for_timeout(int(os.environ.get("CREATOR_METRICS_WAIT_MS", "6000")))
                body = page.locator("body").inner_text(timeout=15000)
                if any(s in body for s in cfg.login_signs):
                    return {"ok": False, "error": "creator_login_required", "platform": plat}

                if target == manage_url or "manage" in manage_url:
                    page.goto(manage_url, wait_until="domcontentloaded", timeout=120_000)
                    page.wait_for_timeout(3000)

                raw = page.evaluate(_EXTRACT_METRICS_JS, post_id)
                parsed = parse_metrics_from_text(body)
                if isinstance(raw, dict):
                    if raw.get("completion_rate") is not None:
                        parsed["completion_rate"] = raw["completion_rate"]
                    if raw.get("ctr") is not None:
                        parsed["ctr"] = raw["ctr"]
                    if raw.get("views_text"):
                        parsed["views"] = dc.parse_count_text(str(raw["views_text"]))
                    if raw.get("likes_text"):
                        parsed["likes"] = dc.parse_count_text(str(raw["likes_text"]))

                if parsed.get("completion_rate") is None and parsed.get("ctr") is None:
                    parsed_text = parse_metrics_from_text(body)
                    parsed.update({k: v for k, v in parsed_text.items() if v is not None})

                if parsed.get("completion_rate") is None and parsed.get("ctr") is None:
                    sample = _sample_metrics(platform=plat, post_url=post_url)
                    sample["hint"] = "creator_page_no_metrics"
                    sample["page_excerpt"] = str((raw or {}).get("page_excerpt") or "")[:200]
                    return sample

                return {
                    "ok": True,
                    "platform": plat,
                    "post_url": post_url,
                    "post_id": post_id,
                    "account_id": account_id,
                    "source": "creator_center",
                    **parsed,
                }
            finally:
                browser.close()
    except Exception as exc:
        out = _sample_metrics(platform=plat, post_url=post_url)
        out["error"] = str(exc)[:300]
        out["source"] = "sample_fallback"
        return out


_TAKEDOWN_JS = """
(postId) => {
  const keywords = ['删除', '下架', '隐藏', '仅自己可见', '撤回'];
  const clicked = [];
  const nodes = Array.from(document.querySelectorAll('button, a, span, div'));
  for (const el of nodes) {
    const t = (el.innerText || '').trim();
    if (!t || t.length > 12) continue;
    if (keywords.some(k => t.includes(k))) {
      try { el.click(); clicked.push(t); break; } catch (e) {}
    }
  }
  return { clicked, post_id: postId, excerpt: (document.body?.innerText || '').slice(0, 300) };
}
"""


def takedown_via_creator(
    *,
    platform: str,
    post_url: str,
    account_id: str = "default",
    action: str = "delete",
) -> dict[str, Any]:
    """创作者中心真实下架/删除（需登录态）。"""
    plat = _plat(platform)
    storage = pub.resolve_storage(plat, account_id=account_id)
    if not storage or not Path(storage).is_file():
        return {"ok": False, "error": "storage_state_missing", "platform": plat}
    if not playwright_installed():
        return {"ok": False, "error": "playwright_not_installed", "platform": plat}

    cfg_fn = PLATFORM_CONFIGS.get(plat)
    if not cfg_fn:
        return {"ok": False, "error": "unsupported_platform", "platform": plat}

    cfg = cfg_fn()
    post_id = _post_id_from_url(post_url)
    headless = pub.env_truthy(cfg.headless_env, "1")
    from services.takedown import takedown_enabled

    try:
        with playwright_sync_context() as p:
            launch_kw: dict[str, Any] = {"headless": headless}
            channel = (os.environ.get("PUBLISH_PLAYWRIGHT_CHANNEL") or "").strip()
            if channel:
                launch_kw["channel"] = channel
            browser = p.chromium.launch(**launch_kw)
            try:
                context = browser.new_context(
                    storage_state=str(Path(storage).resolve()),
                    locale="zh-CN",
                    viewport={"width": 1440, "height": 900},
                    user_agent=pub.DEFAULT_UA,
                )
                page = context.new_page()
                page.goto(cfg.manage_url, wait_until="domcontentloaded", timeout=120_000)
                page.wait_for_timeout(int(os.environ.get("TAKEDOWN_WAIT_MS", "5000")))
                body = page.locator("body").inner_text(timeout=15000)
                if any(s in body for s in cfg.login_signs):
                    return {"ok": False, "error": "creator_login_required", "platform": plat}

                if post_id and post_id not in body:
                    page.goto(post_url, wait_until="domcontentloaded", timeout=120_000)
                    page.wait_for_timeout(3000)

                if not takedown_enabled():
                    return {
                        "ok": True,
                        "dry_run": True,
                        "platform": plat,
                        "post_url": post_url,
                        "action": action,
                        "message": "TAKEDOWN_ENABLED=0，未点击删除",
                    }

                result = page.evaluate(_TAKEDOWN_JS, post_id)
                page.wait_for_timeout(2000)
                # 确认弹窗
                confirm_sels = ['button:has-text("确定")', 'button:has-text("确认")', 'button:has-text("删除")']
                for sel in confirm_sels:
                    try:
                        loc = page.locator(sel).first
                        if loc.count() > 0:
                            loc.click(timeout=5000)
                            break
                    except Exception:
                        continue

                return {
                    "ok": True,
                    "dry_run": False,
                    "platform": plat,
                    "post_url": post_url,
                    "post_id": post_id,
                    "action": action,
                    "creator_result": result,
                    "message": "takedown_action_sent",
                }
            finally:
                browser.close()
    except Exception as exc:
        return {"ok": False, "error": "takedown_failed", "detail": str(exc)[:300], "platform": plat}
