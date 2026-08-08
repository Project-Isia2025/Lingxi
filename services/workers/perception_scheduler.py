"""数据感知定时调度（默认每 30 分钟扫描热榜 + 竞品）。"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
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


def scheduler_enabled() -> bool:
    return os.environ.get("PERCEPTION_SCHEDULE_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def interval_sec() -> int:
    try:
        return max(300, int(os.environ.get("PERCEPTION_INTERVAL_SEC", "1800")))
    except ValueError:
        return 1800


def scan_keywords() -> list[str]:
    raw = (os.environ.get("PERCEPTION_KEYWORDS") or "").strip()
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    try:
        from services.inventory import get_primary_product

        prod = get_primary_product()
        if prod.get("ok"):
            name = str(prod["product"].get("name") or "")
            kw = str(prod["product"].get("keyword") or name)
            if kw:
                return [kw]
    except Exception:
        pass
    return ["护肤"]


def run_scheduled_perception(*, keyword: str | None = None) -> dict[str, Any]:
    from services.douyin.hotlist import fetch_douyin_hotlist
    from services.perception import run_perception_scan

    kw = (keyword or "").strip() or scan_keywords()[0]
    hot = fetch_douyin_hotlist(limit=int(os.environ.get("PERCEPTION_HOTLIST_LIMIT", "10") or 10))
    hot_kw = [str(x.get("keyword") or x.get("title") or "")[:20] for x in hot.get("items") or [] if x.get("keyword") or x.get("title")]
    merged_kw = kw
    if hot_kw:
        merged_kw = hot_kw[0]

    run_id = f"scan-{uuid.uuid4().hex[:10]}"
    result = run_perception_scan(keyword=merged_kw or kw, run_id=run_id, include_hotlist=True)
    summary = {**result, "scan_keyword": merged_kw or kw, "hotlist": hot, "ts": int(time.time())}

    with _LOCK:
        _STATE["last_run_ts"] = summary["ts"]
        _STATE["last_result"] = summary
        _STATE["run_count"] = int(_STATE.get("run_count") or 0) + 1
        _STATE["last_error"] = str(summary.get("error") or "")
        _STATE["running"] = False
    return summary


def get_scheduler_status() -> dict[str, Any]:
    with _LOCK:
        status = {
            "ok": True,
            "enabled": scheduler_enabled(),
            "interval_sec": interval_sec(),
            "keywords": scan_keywords(),
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
        run_scheduled_perception()
    except Exception as exc:
        with _LOCK:
            _STATE["last_error"] = str(exc)
            _STATE["running"] = False
        log.exception("perception scheduler failed")
    finally:
        with _LOCK:
            if _STATE.get("running"):
                _STATE["running"] = False


def _loop() -> None:
    from services.background_leader import wait_or_run_as_leader

    wait_or_run_as_leader(
        "perception-scheduler",
        stop_event=_STOP,
        interval_sec=interval_sec(),
        on_leader=_loop_tick,
    )


def start_perception_scheduler() -> bool:
    if not scheduler_enabled():
        return False
    if use_celery_workers():
        return True
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return True
    _STOP.clear()
    _THREAD = threading.Thread(target=_loop, daemon=True, name="perception-scheduler")
    _THREAD.start()
    return True


def stop_perception_scheduler() -> None:
    _STOP.set()
    if _THREAD:
        _THREAD.join(timeout=5)
