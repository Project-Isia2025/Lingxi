"""发布队列后台 Worker（定时消费 publish_queue）。"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from core.storage import list_publish_queue
from services.publish.scheduler import run_publish_queue
from services.workers.runtime import enrich_worker_status, use_celery_workers

log = logging.getLogger(__name__)

_STATE: dict[str, Any] = {
    "running": False,
    "last_run_ts": 0,
    "last_results": [],
    "last_error": "",
    "run_count": 0,
}
_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
_STOP = threading.Event()


def worker_enabled() -> bool:
    return os.environ.get("PUBLISH_QUEUE_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def worker_interval_sec() -> int:
    try:
        return max(30, int(os.environ.get("PUBLISH_QUEUE_INTERVAL_SEC", "300")))
    except ValueError:
        return 300


def worker_batch_size() -> int:
    try:
        return max(1, int(os.environ.get("PUBLISH_QUEUE_BATCH_SIZE", "5")))
    except ValueError:
        return 5


def run_queue_once(*, limit: int | None = None, dry_run: bool = False) -> dict[str, Any]:
    """执行一批到期发布任务。"""
    try:
        from services.publish_priority import refresh_queue_priorities

        refresh_queue_priorities()
    except Exception:
        pass
    batch = limit if limit is not None else worker_batch_size()
    summary = run_publish_queue(limit=batch, dry_run=dry_run)
    summary["ts"] = int(time.time())
    with _LOCK:
        _STATE["last_run_ts"] = summary["ts"]
        _STATE["last_results"] = summary.get("results") or []
        _STATE["run_count"] = int(_STATE.get("run_count") or 0) + 1
        _STATE["last_error"] = ""
        _STATE["running"] = False
    return summary


def get_worker_status() -> dict[str, Any]:
    pending = len(list_publish_queue(status="queued", limit=200))
    with _LOCK:
        last = _STATE.get("last_results") or []
        status = {
            "ok": True,
            "enabled": worker_enabled(),
            "interval_sec": worker_interval_sec(),
            "batch_size": worker_batch_size(),
            "thread_alive": bool(_THREAD and _THREAD.is_alive()),
            "running": _STATE.get("running"),
            "last_run_ts": _STATE.get("last_run_ts"),
            "run_count": _STATE.get("run_count"),
            "last_error": _STATE.get("last_error"),
            "pending_queued": pending,
            "last_summary": {
                "processed": len(last),
                "success": sum(1 for r in last if r.get("success") or r.get("dry_run")),
            },
        }
    return enrich_worker_status(status)


def _worker_tick() -> None:
    try:
        with _LOCK:
            _STATE["running"] = True
        pending = list_publish_queue(status="queued", limit=1)
        if pending:
            run_queue_once()
        try:
            from services.post_publish_monitor_worker import run_once as poll_monitors

            poll_monitors(limit=3)
        except Exception:
            pass
    except Exception as exc:
        with _LOCK:
            _STATE["last_error"] = str(exc)
            _STATE["running"] = False
        log.exception("publish queue worker failed")
    finally:
        with _LOCK:
            if _STATE.get("running"):
                _STATE["running"] = False


def _worker_loop() -> None:
    from services.background_leader import wait_or_run_as_leader

    wait_or_run_as_leader(
        "publish-queue",
        stop_event=_STOP,
        interval_sec=worker_interval_sec(),
        on_leader=_worker_tick,
    )


def start_background_worker() -> bool:
    """启动后台发布队列 Worker（thread 模式）或确认 Celery 已接管。"""
    if not worker_enabled():
        return False
    if use_celery_workers():
        return True
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return True
    _STOP.clear()
    _THREAD = threading.Thread(target=_worker_loop, daemon=True, name="publish-queue-worker")
    _THREAD.start()
    return True


def stop_background_worker() -> None:
    _STOP.set()
    if _THREAD:
        _THREAD.join(timeout=5)


def trigger_worker_async(*, dry_run: bool = False) -> dict[str, Any]:
    """手动触发一次异步队列消费。"""
    if use_celery_workers():
        from infra.celery_tasks import publish_queue_tick

        if dry_run:
            summary = run_queue_once(dry_run=True)
            return {"ok": True, "mode": "celery_inline", "dry_run": True, "summary": summary}
        async_result = publish_queue_tick.delay()
        return {"ok": True, "mode": "celery", "task_id": async_result.id}

    if _STATE.get("running"):
        return {"ok": False, "error": "worker_already_running"}

    def _once() -> None:
        run_queue_once(dry_run=dry_run)

    t = threading.Thread(target=_once, daemon=True, name="publish-queue-once")
    t.start()
    return {"ok": True, "message": "worker_started", "dry_run": dry_run}
