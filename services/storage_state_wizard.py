"""Playwright 登录态（storage_state）检查与导出目标定义。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import bootstrap


def _root() -> Path:
    return bootstrap.project_root()


STORAGE_TARGETS: dict[str, dict[str, str]] = {
    "douyin_pc": {
        "label": "抖音 PC（爬虫/热榜）",
        "url": "https://www.douyin.com/",
        "out": "data/state/douyin_pc_storage.json",
        "env": "DOUYIN_STORAGE_STATE",
        "purpose": "crawl",
    },
    "douyin_creator": {
        "label": "抖音创作者中心（发布/完播）",
        "url": "https://creator.douyin.com/",
        "out": "data/state/douyin_creator_storage.json",
        "env": "DOUYIN_PUBLISH_STORAGE_STATE",
        "purpose": "publish",
    },
    "xhs_pc": {
        "label": "小红书 PC（爬虫）",
        "url": "https://www.xiaohongshu.com/",
        "out": "data/state/xhs_pc_storage.json",
        "env": "XHS_STORAGE_STATE",
        "purpose": "crawl",
    },
    "xhs_creator": {
        "label": "小红书创作者中心（发布）",
        "url": "https://creator.xiaohongshu.com/",
        "out": "data/state/xhs_creator_storage.json",
        "env": "XHS_PUBLISH_STORAGE_STATE",
        "purpose": "publish",
    },
    "shipinhao_creator": {
        "label": "视频号创作者中心（发布）",
        "url": "https://channels.weixin.qq.com/",
        "out": "data/state/shipinhao_creator_storage.json",
        "env": "SHIPINHAO_PUBLISH_STORAGE_STATE",
        "purpose": "publish",
    },
}


def resolve_target_path(target_id: str) -> Path:
    cfg = STORAGE_TARGETS[target_id]
    raw = (os.environ.get(cfg["env"]) or cfg["out"]).strip()
    p = Path(raw)
    if not p.is_absolute():
        p = _root() / p
    return p


def inspect_storage_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False, "valid": False, "size_bytes": 0, "cookies": 0, "origins": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cookies = data.get("cookies") if isinstance(data.get("cookies"), list) else []
        origins = data.get("origins") if isinstance(data.get("origins"), list) else []
        valid = isinstance(data, dict) and (len(cookies) > 0 or len(origins) > 0)
        return {
            "exists": True,
            "valid": valid,
            "size_bytes": path.stat().st_size,
            "cookies": len(cookies),
            "origins": len(origins),
        }
    except Exception as exc:
        return {"exists": True, "valid": False, "error": str(exc)[:120], "size_bytes": path.stat().st_size}


def storage_target_status(target_id: str) -> dict[str, Any]:
    cfg = STORAGE_TARGETS[target_id]
    path = resolve_target_path(target_id)
    info = inspect_storage_file(path)
    env_val = (os.environ.get(cfg["env"]) or "").strip()
    return {
        "id": target_id,
        "label": cfg["label"],
        "purpose": cfg["purpose"],
        "url": cfg["url"],
        "path": str(path),
        "env": cfg["env"],
        "env_override": env_val,
        "ready": bool(info.get("valid")),
        **info,
    }


def all_storage_status() -> dict[str, Any]:
    rows = [storage_target_status(tid) for tid in STORAGE_TARGETS]
    ready = [r["id"] for r in rows if r.get("ready")]
    missing = [r["id"] for r in rows if not r.get("ready")]
    return {
        "ok": True,
        "targets": rows,
        "ready": ready,
        "missing": missing,
        "publish_ready": all(
            storage_target_status(t).get("ready")
            for t in ("douyin_creator",)
            if t in STORAGE_TARGETS
        ),
    }


def export_storage_state(*, target_id: str, headless: bool = False) -> dict[str, Any]:
    """打开浏览器导出指定 target 的 storage_state。"""
    if target_id not in STORAGE_TARGETS:
        return {"ok": False, "error": "unknown_target", "target_id": target_id}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "error": "playwright_not_installed"}

    cfg = STORAGE_TARGETS[target_id]
    out = resolve_target_path(target_id)
    out.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, channel="chrome")
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
        page = context.new_page()
        page.goto(cfg["url"], wait_until="domcontentloaded")
        input(f"[{cfg['label']}] 请在浏览器登录 {cfg['url']} ，完成后按 Enter 保存… ")
        context.storage_state(path=str(out))
        browser.close()

    info = inspect_storage_file(out)
    return {
        "ok": bool(info.get("valid")),
        "target_id": target_id,
        "path": str(out),
        "env": cfg["env"],
        "env_line": f"{cfg['env']}={out}",
        **info,
    }
