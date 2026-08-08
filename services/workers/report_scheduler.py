"""ROI 报表定时发送。"""
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


def report_scheduler_enabled() -> bool:
    return os.environ.get("ROI_REPORT_SCHEDULE_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def report_interval_sec() -> int:
    try:
        return max(3600, int(os.environ.get("ROI_REPORT_INTERVAL_SEC", "86400")))
    except ValueError:
        return 86400


def report_days() -> int:
    try:
        return max(1, min(int(os.environ.get("ROI_REPORT_DAYS", "30")), 90))
    except ValueError:
        return 30


def run_scheduled_report() -> dict[str, Any]:
    from services.roi_email import send_roi_report_email

    result = send_roi_report_email(days=report_days())
    summary = {**result, "ts": int(time.time())}
    with _LOCK:
        _STATE["last_run_ts"] = summary["ts"]
        _STATE["last_result"] = result
        _STATE["run_count"] = int(_STATE.get("run_count") or 0) + 1
        _STATE["last_error"] = str(result.get("error") or "")
        _STATE["running"] = False
    return summary


def get_report_scheduler_status() -> dict[str, Any]:
    with _LOCK:
        status = {
            "ok": True,
            "enabled": report_scheduler_enabled(),
            "interval_sec": report_interval_sec(),
            "report_days": report_days(),
            "thread_alive": bool(_THREAD and _THREAD.is_alive()),
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
        run_scheduled_report()
    except Exception as exc:
        with _LOCK:
            _STATE["last_error"] = str(exc)
            _STATE["running"] = False
        log.exception("roi report scheduler failed")
    finally:
        with _LOCK:
            if _STATE.get("running"):
                _STATE["running"] = False


def _loop() -> None:
    from services.background_leader import wait_or_run_as_leader

    wait_or_run_as_leader(
        "roi-report-scheduler",
        stop_event=_STOP,
        interval_sec=report_interval_sec(),
        on_leader=_loop_tick,
    )


def start_report_scheduler() -> bool:
    if not report_scheduler_enabled():
        return False
    if use_celery_workers():
        return True
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return True
    _STOP.clear()
    _THREAD = threading.Thread(target=_loop, daemon=True, name="roi-report-scheduler")
    _THREAD.start()
    return True


def stop_report_scheduler() -> None:
    _STOP.set()
    if _THREAD:
        _THREAD.join(timeout=5)
