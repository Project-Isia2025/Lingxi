"""发布队列限流：多 run 矩阵入队错峰调度。"""
from __future__ import annotations

import os
import time
from typing import Any


def rate_limit_enabled() -> bool:
    return os.environ.get("PUBLISH_RATE_LIMIT_ENABLED", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def min_interval_sec() -> int:
    try:
        return max(30, int(os.environ.get("PUBLISH_MIN_INTERVAL_SEC", "300")))
    except ValueError:
        return 300


def matrix_stagger_sec() -> int:
    try:
        return max(15, int(os.environ.get("MATRIX_RUN_STAGGER_SEC", "120")))
    except ValueError:
        return 120


def max_queued_per_run() -> int:
    try:
        return max(1, int(os.environ.get("PUBLISH_MAX_QUEUED_PER_RUN", "12")))
    except ValueError:
        return 12


def max_queued_per_account() -> int:
    try:
        return max(1, int(os.environ.get("PUBLISH_MAX_QUEUED_PER_ACCOUNT", "20")))
    except ValueError:
        return 20


def rate_limit_config() -> dict[str, Any]:
    return {
        "enabled": rate_limit_enabled(),
        "min_interval_sec": min_interval_sec(),
        "matrix_stagger_sec": matrix_stagger_sec(),
        "max_queued_per_run": max_queued_per_run(),
        "max_queued_per_account": max_queued_per_account(),
    }


def resolve_scheduled_ts(
    *,
    platform: str,
    account_id: str,
    run_id: str = "",
    requested_ts: int = 0,
) -> dict[str, Any]:
    """为入队任务计算 scheduled_ts，同账号间隔 + 同 run 矩阵错峰。"""
    now = int(time.time())
    if not rate_limit_enabled():
        ts = int(requested_ts or now)
        return {"ok": True, "scheduled_ts": ts, "rate_limited": False}

    from core.storage import list_publish_queue_items

    queued = list_publish_queue_items(status="queued", limit=300)
    plat = (platform or "douyin").strip().lower()
    aid = (account_id or "default").strip()
    rid = (run_id or "").strip()

    same_account = [
        j for j in queued
        if str(j.get("platform") or "").lower() == plat and str(j.get("account_id") or "") == aid
    ]
    if len(same_account) >= max_queued_per_account():
        return {
            "ok": False,
            "error": "account_queue_limit",
            "platform": plat,
            "account_id": aid,
            "limit": max_queued_per_account(),
        }

    same_run = [j for j in queued if rid and str(j.get("run_id") or "") == rid]
    if rid and len(same_run) >= max_queued_per_run():
        return {
            "ok": False,
            "error": "run_queue_limit",
            "run_id": rid,
            "limit": max_queued_per_run(),
        }

    base = max(now, int(requested_ts or 0))
    if same_account:
        last_sched = max(int(j.get("scheduled_ts") or 0) for j in same_account)
        base = max(base, last_sched + min_interval_sec())

    stagger_index = len(same_run)
    if rid and stagger_index > 0:
        base = max(base, now + stagger_index * matrix_stagger_sec())

    return {
        "ok": True,
        "scheduled_ts": base,
        "rate_limited": True,
        "stagger_index": stagger_index,
        "account_queued": len(same_account),
        "run_queued": len(same_run),
    }
