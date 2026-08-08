"""Worker 运行时模式：Celery（默认）或 legacy 线程 + Leader Lock。"""
from __future__ import annotations

import os
from typing import Any

_TRUE = {"1", "true", "yes", "on"}


def worker_backend() -> str:
    """返回 ``celery`` 或 ``thread``。"""
    raw = (os.environ.get("WORKER_BACKEND") or "celery").strip().lower()
    return raw if raw in ("celery", "thread") else "celery"


def use_celery_workers() -> bool:
    return worker_backend() == "celery"


def use_thread_workers() -> bool:
    return worker_backend() == "thread"


def worker_active(status: dict[str, Any]) -> bool:
    """判断 worker 是否处于「已启用且运行中」状态（供 Dashboard / 就绪检查）。"""
    if not status.get("enabled"):
        return False
    if status.get("worker_backend") == "celery":
        try:
            from infra.worker_health import celery_worker_online

            return celery_worker_online()
        except Exception:
            return False
    return bool(status.get("thread_alive"))


def enrich_worker_status(status: dict[str, Any]) -> dict[str, Any]:
    """为各 worker status 注入 backend 与 active 字段。"""
    status = dict(status)
    status["worker_backend"] = worker_backend()
    status["active"] = worker_active(status)
    return status
