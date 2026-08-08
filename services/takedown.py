"""发布后内容下架（创作者中心 / API）。"""
from __future__ import annotations

import os
from typing import Any


def takedown_enabled() -> bool:
    return os.environ.get("TAKEDOWN_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def takedown_post(*, platform: str, post_url: str, run_id: str = "", reason: str = "") -> dict[str, Any]:
    """下架或隐藏已发布内容。默认 dry-run 仅记录。"""
    plat = (platform or "douyin").strip().lower()
    if plat == "xhs":
        plat = "xiaohongshu"

    if not takedown_enabled():
        return {
            "ok": True,
            "dry_run": True,
            "platform": plat,
            "post_url": post_url,
            "run_id": run_id,
            "reason": reason,
            "message": "TAKEDOWN_ENABLED=0，仅记录不下架",
        }

    creator_result: dict[str, Any] = {"ok": False, "error": "not_attempted"}
    try:
        from services.creator_center import takedown_via_creator

        creator_result = takedown_via_creator(platform=plat, post_url=post_url)
    except Exception as exc:
        creator_result = {"ok": False, "error": str(exc)[:200]}

    try:
        from core.storage import metrics_record, save_episodic

        metrics_record(
            run_id=run_id or "takedown",
            event_type="takedown",
            value=1.0,
            payload={
                "platform": plat,
                "post_url": post_url,
                "reason": reason,
                "creator": creator_result,
            },
        )
        save_episodic(
            run_id=run_id or "takedown",
            agent="execution",
            observation=f"已触发下架：{reason[:80]}",
            action="takedown_post",
            payload={"platform": plat, "post_url": post_url, "creator": creator_result},
        )
    except Exception:
        pass

    return {
        "ok": bool(creator_result.get("ok")),
        "dry_run": bool(creator_result.get("dry_run")),
        "platform": plat,
        "post_url": post_url,
        "run_id": run_id,
        "reason": reason,
        "creator": creator_result,
        "message": creator_result.get("message") or "takedown_recorded",
    }
