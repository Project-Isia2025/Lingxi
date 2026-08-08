"""发布后监控后台 Worker。"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

log = logging.getLogger(__name__)

from services.workers.runtime import enrich_worker_status, use_celery_workers

_STATE: dict[str, Any] = {
    "running": False,
    "last_run_ts": 0,
    "last_result": {},
    "last_error": "",
    "run_count": 0,
}
_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
_STOP = threading.Event()


def worker_enabled() -> bool:
    return os.environ.get("POST_PUBLISH_MONITOR_ENABLED", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def interval_sec() -> int:
    try:
        return max(300, int(os.environ.get("POST_PUBLISH_MONITOR_INTERVAL_SEC", "1800")))
    except ValueError:
        return 1800


def run_once(*, limit: int = 5) -> dict[str, Any]:
    from services.post_publish_monitor import poll_due_monitors

    summary = poll_due_monitors(limit=limit)
    summary["ts"] = int(time.time())
    with _LOCK:
        _STATE["last_run_ts"] = summary["ts"]
        _STATE["last_result"] = summary
        _STATE["run_count"] = int(_STATE.get("run_count") or 0) + 1
        _STATE["last_error"] = ""
        _STATE["running"] = False
    return summary


def get_status() -> dict[str, Any]:
    from core.storage import list_post_monitors

    pending = list_post_monitors(status="pending", limit=100)
    with _LOCK:
        status = {
            "ok": True,
            "enabled": worker_enabled(),
            "interval_sec": interval_sec(),
            "thread_alive": bool(_THREAD and _THREAD.is_alive()),
            "pending_count": len(pending),
            "running": _STATE.get("running"),
            "last_run_ts": _STATE.get("last_run_ts"),
            "run_count": _STATE.get("run_count"),
            "last_error": _STATE.get("last_error"),
            "last_result": _STATE.get("last_result"),
        }
    return enrich_worker_status(status)


def _loop_tick() -> None:
    try:
        with _LOCK:
            _STATE["running"] = True
        run_once()
    except Exception as exc:
        with _LOCK:
            _STATE["last_error"] = str(exc)
            _STATE["running"] = False
        log.exception("post publish monitor worker failed")
    finally:
        with _LOCK:
            if _STATE.get("running"):
                _STATE["running"] = False


def _loop() -> None:
    from services.background_leader import wait_or_run_as_leader

    wait_or_run_as_leader(
        "post-publish-monitor",
        stop_event=_STOP,
        interval_sec=interval_sec(),
        on_leader=_loop_tick,
    )


def start_monitor_worker() -> bool:
    if not worker_enabled():
        return False
    if use_celery_workers():
        return True
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return True
    _STOP.clear()
    _THREAD = threading.Thread(target=_loop, daemon=True, name="post-publish-monitor")
    _THREAD.start()
    return True


def stop_monitor_worker() -> None:
    _STOP.set()
    if _THREAD:
        _THREAD.join(timeout=5)
