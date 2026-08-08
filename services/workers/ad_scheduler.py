"""投流报表定时轮询。"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from core.storage import list_ad_campaigns
from services.ad_feedback import sync_ad_report_for_run
from services.workers.runtime import enrich_worker_status, use_celery_workers

log = logging.getLogger(__name__)

_STATE: dict[str, Any] = {
    "running": False,
    "thread_alive": False,
    "last_poll_ts": 0,
    "last_results": [],
    "last_error": "",
    "poll_count": 0,
}
_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
_STOP = threading.Event()


def poll_enabled() -> bool:
    return os.environ.get("AD_POLL_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def poll_interval_sec() -> int:
    try:
        return max(60, int(os.environ.get("AD_POLL_INTERVAL_SEC", "3600")))
    except ValueError:
        return 3600


def poll_all_campaigns(*, days: int = 7, limit: int = 50) -> dict[str, Any]:
    """同步所有已记录 campaign 的投流报表。"""
    items = list_ad_campaigns(limit=limit)
    results: list[dict[str, Any]] = []
    ok_n = 0
    for row in items:
        run_id = str(row.get("run_id") or "")
        if not run_id:
            continue
        try:
            out = sync_ad_report_for_run(run_id, days=days)
            if out.get("ok"):
                ok_n += 1
                try:
                    from services.ad_bid_engine import auto_bid_enabled, run_auto_bid_for_run

                    if auto_bid_enabled():
                        out["auto_bid"] = run_auto_bid_for_run(run_id, apply=True)
                except Exception as exc:
                    out["auto_bid_error"] = str(exc)
            results.append({"run_id": run_id, **out})
        except Exception as exc:
            results.append({"run_id": run_id, "ok": False, "error": str(exc)})

    summary = {
        "ok": True,
        "polled": len(results),
        "success": ok_n,
        "failed": len(results) - ok_n,
        "results": results,
        "ts": int(time.time()),
    }
    with _LOCK:
        _STATE["last_poll_ts"] = summary["ts"]
        _STATE["last_results"] = results
        _STATE["poll_count"] = int(_STATE.get("poll_count") or 0) + 1
        _STATE["last_error"] = ""
        _STATE["running"] = False
    return summary


def get_poll_status() -> dict[str, Any]:
    with _LOCK:
        status = {
            "ok": True,
            "enabled": poll_enabled(),
            "interval_sec": poll_interval_sec(),
            "thread_alive": bool(_THREAD and _THREAD.is_alive()),
            "running": _STATE.get("running"),
            "last_poll_ts": _STATE.get("last_poll_ts"),
            "poll_count": _STATE.get("poll_count"),
            "last_error": _STATE.get("last_error"),
            "last_summary": {
                "polled": len(_STATE.get("last_results") or []),
                "success": sum(1 for r in (_STATE.get("last_results") or []) if r.get("ok")),
            },
        }
    return enrich_worker_status(status)


def _poll_tick() -> None:
    try:
        with _LOCK:
            _STATE["running"] = True
        poll_all_campaigns()
    except Exception as exc:
        with _LOCK:
            _STATE["last_error"] = str(exc)
            _STATE["running"] = False
        log.exception("ad poll failed")
    finally:
        with _LOCK:
            if _STATE.get("running"):
                _STATE["running"] = False


def _poll_loop() -> None:
    from services.background_leader import wait_or_run_as_leader

    wait_or_run_as_leader(
        "ad-report-poller",
        stop_event=_STOP,
        interval_sec=poll_interval_sec(),
        on_leader=_poll_tick,
    )


def start_background_poller() -> bool:
    """启动后台轮询（thread 模式）或确认 Celery 已接管。"""
    if not poll_enabled():
        return False
    if use_celery_workers():
        return True
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return True
    _STOP.clear()
    _THREAD = threading.Thread(target=_poll_loop, daemon=True, name="ad-report-poller")
    _THREAD.start()
    with _LOCK:
        _STATE["thread_alive"] = True
    return True


def stop_background_poller() -> None:
    _STOP.set()
    if _THREAD:
        _THREAD.join(timeout=5)


def trigger_poll_async() -> dict[str, Any]:
    """手动触发一次异步轮询。"""
    if use_celery_workers():
        from infra.celery_tasks import ad_poll_tick

        async_result = ad_poll_tick.delay()
        return {"ok": True, "mode": "celery", "task_id": async_result.id}

    if _STATE.get("running"):
        return {"ok": False, "error": "poll_already_running"}

    def _worker() -> None:
        poll_all_campaigns()

    t = threading.Thread(target=_worker, daemon=True, name="ad-poll-once")
    t.start()
    return {"ok": True, "message": "poll_started"}
