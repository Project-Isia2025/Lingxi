"""Playwright 创作者中心发布就绪检查。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from services.publish.common import build_metadata, publish_enabled, resolve_storage, validate_video_path
from services.publish.playwright_util import playwright_installed
from services.publish.router import health, supported_platforms
from services.storage_state_wizard import STORAGE_TARGETS, inspect_storage_file, resolve_target_path


def _platform_storage_target(platform: str) -> str:
    mapping = {
        "douyin": "douyin_creator",
        "xiaohongshu": "xhs_creator",
        "xhs": "xhs_creator",
        "shipinhao": "shipinhao_creator",
    }
    return mapping.get(platform.lower(), "")


def platform_readiness(platform: str) -> dict[str, Any]:
    plat = platform.strip().lower()
    if plat == "xhs":
        plat = "xiaohongshu"
    h = health(plat)
    storage = resolve_storage(plat)
    target_id = _platform_storage_target(plat)
    wizard = {}
    if target_id and target_id in STORAGE_TARGETS:
        path = resolve_target_path(target_id)
        wizard = inspect_storage_file(path)
    ready = bool(
        playwright_installed()
        and publish_enabled(plat)
        and h.get("storage_exists")
        and (wizard.get("valid") or Path(storage).is_file())
    )
    return {
        "platform": plat,
        "playwright_installed": playwright_installed(),
        "publish_enabled": publish_enabled(plat),
        "storage_path": storage or None,
        "storage_exists": bool(storage),
        "storage_valid": bool(wizard.get("valid")),
        "ready": ready,
        "health": h,
    }


def all_publish_readiness() -> dict[str, Any]:
    rows = [platform_readiness(p) for p in supported_platforms()]
    ready = [r["platform"] for r in rows if r.get("ready")]
    return {
        "ok": True,
        "platforms": rows,
        "ready": ready,
        "missing": [r["platform"] for r in rows if not r.get("ready")],
        "playwright_installed": playwright_installed(),
        "setup_hint": (
            "运行 python scripts/export_storage_wizard.py --export douyin_creator 导出登录态"
            if not ready
            else f"发布就绪平台: {', '.join(ready)}"
        ),
    }


def dry_run_publish_check(*, platform: str, video_path: str, script: str, title: str = "") -> dict[str, Any]:
    from services.publish.router import publish_to_platform

    ok, err = validate_video_path(video_path)
    if not ok:
        return {"ok": False, "error": err, "platform": platform}
    meta = build_metadata(script=script, title=title)
    result = publish_to_platform(
        platform,
        video_path=video_path,
        script=script,
        title=title,
        dry_run=True,
    )
    return {
        "ok": bool(result.get("success")),
        "platform": platform,
        "dry_run": True,
        "metadata": meta,
        "result": result,
    }
