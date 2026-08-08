"""后台 Worker 健康探测（Celery / thread）。"""
from __future__ import annotations

import os
import time
from typing import Any

_CACHE: dict[str, Any] = {"ts": 0.0, "online": False}


def _any_worker_enabled() -> bool:
    flags = (
        "PUBLISH_QUEUE_ENABLED",
        "AD_POLL_ENABLED",
        "PERCEPTION_SCHEDULE_ENABLED",
        "ROI_REPORT_SCHEDULE_ENABLED",
        "ROI_ALERT_CLEANUP_ENABLED",
        "POST_PUBLISH_MONITOR_ENABLED",
        "TASK_CLEANUP_ENABLED",
    )
    return any(os.environ.get(name, "0" if name != "ROI_ALERT_CLEANUP_ENABLED" else "1").strip().lower() in ("1", "true", "yes", "on") for name in flags)


def celery_worker_online(*, timeout: float = 2.0, cache_sec: float = 15.0) -> bool:
    """探测 Celery worker 是否在线（带短缓存）。"""
    now = time.time()
    if now - float(_CACHE.get("ts") or 0) < cache_sec:
        return bool(_CACHE.get("online"))

    online = False
    try:
        from infra.health import check_celery_worker

        result = check_celery_worker(timeout=timeout)
        online = bool(result.get("ok"))
    except Exception:
        online = False

    _CACHE["ts"] = now
    _CACHE["online"] = online
    return online


def celery_workers_required() -> bool:
    backend = (os.environ.get("WORKER_BACKEND") or "celery").strip().lower()
    return backend == "celery" and _any_worker_enabled()
