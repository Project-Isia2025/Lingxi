"""Celery 业务 Worker 任务 — 替代 API 进程内线程 + Redis Leader Lock。"""
from __future__ import annotations

import logging
from typing import Any

from infra.task_queue import celery_app

log = logging.getLogger(__name__)


def _task_enabled(env_name: str, default: str = "0") -> bool:
    import os

    return os.environ.get(env_name, default).strip().lower() in ("1", "true", "yes", "on")


@celery_app.task(name="commerce_agent.tasks.publish_queue_tick", bind=True, max_retries=0)
def publish_queue_tick(self) -> dict[str, Any]:
    if not _task_enabled("PUBLISH_QUEUE_ENABLED"):
        return {"ok": True, "skipped": True, "reason": "disabled"}
    from core.storage import list_publish_queue
    from services.workers.publish_worker import run_queue_once

    try:
        pending = list_publish_queue(status="queued", limit=1)
        summary: dict[str, Any] = {"ok": True, "processed": 0}
        if pending:
            summary = run_queue_once()
        try:
            from services.workers.post_publish_monitor_worker import run_once as poll_monitors

            summary["monitor"] = poll_monitors(limit=3)
        except Exception as exc:
            summary["monitor_error"] = str(exc)
        return summary
    except Exception as exc:
        log.exception("celery publish_queue_tick failed")
        return {"ok": False, "error": str(exc)}


@celery_app.task(name="commerce_agent.tasks.ad_poll_tick", bind=True, max_retries=0)
def ad_poll_tick(self) -> dict[str, Any]:
    if not _task_enabled("AD_POLL_ENABLED"):
        return {"ok": True, "skipped": True, "reason": "disabled"}
    from services.workers.ad_scheduler import poll_all_campaigns

    try:
        return poll_all_campaigns()
    except Exception as exc:
        log.exception("celery ad_poll_tick failed")
        return {"ok": False, "error": str(exc)}


@celery_app.task(name="commerce_agent.tasks.roi_report_tick", bind=True, max_retries=0)
def roi_report_tick(self) -> dict[str, Any]:
    if not _task_enabled("ROI_REPORT_SCHEDULE_ENABLED"):
        return {"ok": True, "skipped": True, "reason": "disabled"}
    from services.workers.report_scheduler import run_scheduled_report

    try:
        return run_scheduled_report()
    except Exception as exc:
        log.exception("celery roi_report_tick failed")
        return {"ok": False, "error": str(exc)}


@celery_app.task(name="commerce_agent.tasks.alert_cleanup_tick", bind=True, max_retries=0)
def alert_cleanup_tick(self) -> dict[str, Any]:
    if not _task_enabled("ROI_ALERT_CLEANUP_ENABLED", "1"):
        return {"ok": True, "skipped": True, "reason": "disabled"}
    from services.workers.alert_cleanup_scheduler import run_alert_cleanup

    try:
        return run_alert_cleanup()
    except Exception as exc:
        log.exception("celery alert_cleanup_tick failed")
        return {"ok": False, "error": str(exc)}


@celery_app.task(name="commerce_agent.tasks.perception_tick", bind=True, max_retries=0)
def perception_tick(self) -> dict[str, Any]:
    if not _task_enabled("PERCEPTION_SCHEDULE_ENABLED"):
        return {"ok": True, "skipped": True, "reason": "disabled"}
    from services.workers.perception_scheduler import run_scheduled_perception

    try:
        return run_scheduled_perception()
    except Exception as exc:
        log.exception("celery perception_tick failed")
        return {"ok": False, "error": str(exc)}


@celery_app.task(name="commerce_agent.tasks.post_publish_monitor_tick", bind=True, max_retries=0)
def post_publish_monitor_tick(self) -> dict[str, Any]:
    if not _task_enabled("POST_PUBLISH_MONITOR_ENABLED", "1"):
        return {"ok": True, "skipped": True, "reason": "disabled"}
    from services.workers.post_publish_monitor_worker import run_once

    try:
        return run_once()
    except Exception as exc:
        log.exception("celery post_publish_monitor_tick failed")
        return {"ok": False, "error": str(exc)}


@celery_app.task(name="commerce_agent.tasks.task_cleanup_tick", bind=True, max_retries=0)
def task_cleanup_tick(self) -> dict[str, Any]:
    if not _task_enabled("TASK_CLEANUP_ENABLED", "1"):
        return {"ok": True, "skipped": True, "reason": "disabled"}
    from services.task_cleanup import purge_all_completed_tasks

    try:
        return purge_all_completed_tasks()
    except Exception as exc:
        log.exception("celery task_cleanup_tick failed")
        return {"ok": False, "error": str(exc)}
