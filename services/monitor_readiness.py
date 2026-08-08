"""完播监控与下架链路就绪检查。"""
from __future__ import annotations

from typing import Any

from services.post_publish_monitor import completion_rate_min, ctr_min, monitor_enabled
from services.post_publish_monitor_worker import get_status, worker_enabled
from services.takedown import takedown_enabled


def monitor_readiness_status(*, platform: str = "douyin", account_id: str = "default") -> dict[str, Any]:
    """检查发布后监控、创作者中心回采与下架配置。"""
    plat = (platform or "douyin").strip().lower()
    if plat == "xhs":
        plat = "xiaohongshu"

    playwright_ok = False
    try:
        from services.publish.playwright_util import playwright_installed

        playwright_ok = playwright_installed()
    except Exception:
        pass

    storage = ""
    try:
        from services.publish.common import resolve_storage

        storage = resolve_storage(plat, account_id=account_id) or ""
    except Exception:
        pass

    creator_enabled = False
    try:
        from services.creator_center import creator_metrics_enabled

        creator_enabled = creator_metrics_enabled()
    except Exception:
        pass

    worker = get_status()
    live_ready = playwright_ok and bool(storage) and creator_enabled

    return {
        "ok": True,
        "monitor_enabled": monitor_enabled(),
        "worker_enabled": worker_enabled(),
        "takedown_enabled": takedown_enabled(),
        "takedown_dry_run": not takedown_enabled(),
        "completion_rate_min": completion_rate_min(),
        "ctr_min": ctr_min(),
        "playwright_installed": playwright_ok,
        "creator_metrics_enabled": creator_enabled,
        "storage_state": storage or None,
        "platform": plat,
        "live_metrics_ready": live_ready,
        "live_takedown_ready": live_ready and takedown_enabled(),
        "worker": {
            "pending_count": worker.get("pending_count"),
            "thread_alive": worker.get("thread_alive"),
            "interval_sec": worker.get("interval_sec"),
        },
        "hints": {
            "dry_run_e2e": "python scripts/acceptance_monitor_e2e.py",
            "enable_takedown": "TAKEDOWN_ENABLED=1（谨慎，将真实下架）",
            "export_storage": "python scripts/export_storage_wizard.py --export douyin_creator",
        },
    }
