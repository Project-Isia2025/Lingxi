"""Celery 任务队列配置。"""
from __future__ import annotations

import os

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()

from celery import Celery

from infra.celery_schedule import build_beat_schedule

_broker = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/1")
_backend = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

celery_app = Celery(
    "commerce_agent",
    broker=_broker,
    backend=_backend,
    include=["infra.celery_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule=build_beat_schedule(),
)

# 确保任务模块已注册
import infra.celery_tasks  # noqa: E402,F401


@celery_app.on_after_configure.connect
def _configure_beat_schedule(sender, **kwargs) -> None:
    sender.conf.beat_schedule = build_beat_schedule()


try:
    from celery.signals import worker_process_init

    @worker_process_init.connect
    def _init_worker_storage(**kwargs) -> None:
        from core.db import init_storage

        init_storage()
except Exception:
    pass


@celery_app.task(name="commerce_agent.health_check")
def health_check() -> dict:
    return {"status": "ok", "worker": "commerce_agent"}


@celery_app.task(name="commerce_agent.echo")
def echo_task(message: str) -> dict:
    return {"echo": message, "status": "ok"}


def verify_worker(timeout: float = 10.0) -> dict:
    """投递 health_check 并等待 worker 返回。"""
    result = health_check.apply_async()
    return result.get(timeout=timeout)


def refresh_beat_schedule() -> dict[str, str]:
    """重新加载 beat 调度（配置变更后调用）。"""
    celery_app.conf.beat_schedule = build_beat_schedule()
    return {name: entry["task"] for name, entry in celery_app.conf.beat_schedule.items()}


def dispatch_task(task_name: str, **kwargs) -> dict:
    """按任务名异步投递业务 tick（供 API 手动触发）。"""
    task = celery_app.tasks.get(task_name)
    if task is None:
        return {"ok": False, "error": f"unknown_task:{task_name}"}
    async_result = task.apply_async(kwargs=kwargs)
    return {"ok": True, "task_id": async_result.id, "task": task_name}
