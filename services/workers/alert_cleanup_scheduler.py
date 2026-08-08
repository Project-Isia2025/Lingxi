"""告警去重日志定时清理。"""
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


def alert_cleanup_enabled() -> bool:
    return os.environ.get("ROI_ALERT_CLEANUP_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")


def cleanup_interval_sec() -> int:
    try:
        return max(3600, int(os.environ.get("ROI_ALERT_CLEANUP_INTERVAL_SEC", "86400")))
    except ValueError:
        return 86400


def cleanup_retention_sec() -> int:
    try:
        return max(86400, int(os.environ.get("ROI_ALERT_CLEANUP_RETENTION_SEC", "604800")))
    except ValueError:
        return 604800


def run_alert_cleanup(*, retention_sec: int | None = None) -> dict[str, Any]:
    from core.storage import count_alert_sent_log, purge_expired_alert_logs

    retention = int(retention_sec or cleanup_retention_sec())
    before = count_alert_sent_log()
    purge = purge_expired_alert_logs(older_than_sec=retention)
    after = count_alert_sent_log()
    summary = {
        "ok": True,
        "retention_sec": retention,
        "before_count": before,
        "after_count": after,
        **purge,
        "ts": int(time.time()),
    }
    with _LOCK:
        _STATE["last_run_ts"] = summary["ts"]
        _STATE["last_result"] = summary
        _STATE["run_count"] = int(_STATE.get("run_count") or 0) + 1
        _STATE["last_error"] = ""
        _STATE["running"] = False
    return summary


def get_alert_cleanup_status() -> dict[str, Any]:
    from core.storage import count_alert_sent_log

    with _LOCK:
        status = {
            "ok": True,
            "enabled": alert_cleanup_enabled(),
            "interval_sec": cleanup_interval_sec(),
            "retention_sec": cleanup_retention_sec(),
            "thread_alive": bool(_THREAD and _THREAD.is_alive()),
            "running": _STATE.get("running"),
            "last_run_ts": _STATE.get("last_run_ts"),
            "run_count": _STATE.get("run_count"),
            "last_error": _STATE.get("last_error"),
            "last_result": _STATE.get("last_result"),
            "log_count": count_alert_sent_log(),
        }
    return enrich_worker_status(status)


def _loop_tick() -> None:
    try:
        with _LOCK:
            _STATE["running"] = True
        run_alert_cleanup()
    except Exception as exc:
        with _LOCK:
            _STATE["last_error"] = str(exc)
            _STATE["running"] = False
        log.exception("alert cleanup scheduler failed")
    finally:
        with _LOCK:
            if _STATE.get("running"):
                _STATE["running"] = False


def _loop() -> None:
    from services.background_leader import wait_or_run_as_leader

    wait_or_run_as_leader(
        "alert-cleanup-scheduler",
        stop_event=_STOP,
        interval_sec=cleanup_interval_sec(),
        on_leader=_loop_tick,
    )


def start_alert_cleanup_scheduler() -> bool:
    if not alert_cleanup_enabled():
        return False
    if use_celery_workers():
        return True
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return True
    _STOP.clear()
    _THREAD = threading.Thread(target=_loop, daemon=True, name="alert-cleanup-scheduler")
    _THREAD.start()
    return True


def stop_alert_cleanup_scheduler() -> None:
    _STOP.set()
    if _THREAD:
        _THREAD.join(timeout=5)
