"""后台 Worker Leader 辅助 — 循环任务前检查/等待锁。"""
from __future__ import annotations

import time
from typing import Callable

from infra.leader_lock import leader_lock_enabled, lock_ttl_sec, try_acquire_leader


def wait_or_run_as_leader(
    lock_name: str,
    *,
    stop_event,
    interval_sec: int,
    on_leader: Callable[[], None],
) -> None:
    """在循环中仅 leader 实例执行 on_leader；非 leader 短睡后重试。"""
    ttl = max(lock_ttl_sec(), interval_sec + 30)
    while not stop_event.is_set():
        if try_acquire_leader(lock_name, ttl_sec=ttl):
            on_leader()
            wait_sec = interval_sec
        else:
            wait_sec = min(30, max(5, interval_sec // 4)) if leader_lock_enabled() else interval_sec
        if stop_event.wait(wait_sec):
            break
