"""Celery Beat 调度表 — 按环境变量开关与间隔生成。"""
from __future__ import annotations

import os
from typing import Any

from celery.schedules import schedule


def _enabled(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _int_env(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def build_beat_schedule() -> dict[str, dict[str, Any]]:
    """根据 worker 开关构建 beat_schedule（仅包含已启用的任务）。"""
    entries: dict[str, dict[str, Any]] = {}

    if _enabled("PUBLISH_QUEUE_ENABLED"):
        entries["publish-queue"] = {
            "task": "commerce_agent.tasks.publish_queue_tick",
            "schedule": schedule(run_every=_int_env("PUBLISH_QUEUE_INTERVAL_SEC", 300, minimum=30)),
        }

    if _enabled("AD_POLL_ENABLED"):
        entries["ad-report-poller"] = {
            "task": "commerce_agent.tasks.ad_poll_tick",
            "schedule": schedule(run_every=_int_env("AD_POLL_INTERVAL_SEC", 3600, minimum=60)),
        }

    if _enabled("ROI_REPORT_SCHEDULE_ENABLED"):
        entries["roi-report-scheduler"] = {
            "task": "commerce_agent.tasks.roi_report_tick",
            "schedule": schedule(run_every=_int_env("ROI_REPORT_INTERVAL_SEC", 86400, minimum=3600)),
        }

    if _enabled("ROI_ALERT_CLEANUP_ENABLED", "1"):
        entries["alert-cleanup-scheduler"] = {
            "task": "commerce_agent.tasks.alert_cleanup_tick",
            "schedule": schedule(run_every=_int_env("ROI_ALERT_CLEANUP_INTERVAL_SEC", 86400, minimum=3600)),
        }

    if _enabled("PERCEPTION_SCHEDULE_ENABLED"):
        entries["perception-scheduler"] = {
            "task": "commerce_agent.tasks.perception_tick",
            "schedule": schedule(run_every=_int_env("PERCEPTION_INTERVAL_SEC", 1800, minimum=300)),
        }

    if _enabled("POST_PUBLISH_MONITOR_ENABLED", "1"):
        entries["post-publish-monitor"] = {
            "task": "commerce_agent.tasks.post_publish_monitor_tick",
            "schedule": schedule(run_every=_int_env("POST_PUBLISH_MONITOR_INTERVAL_SEC", 1800, minimum=300)),
        }

    if _enabled("TASK_CLEANUP_ENABLED", "1"):
        entries["task-cleanup"] = {
            "task": "commerce_agent.tasks.task_cleanup_tick",
            "schedule": schedule(run_every=_int_env("TASK_CLEANUP_INTERVAL_SEC", 86400, minimum=3600)),
        }

    return entries
