"""Celery Worker 替代线程 + Leader Lock 测试。"""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


def test_worker_backend_default_celery():
    from services.workers.runtime import use_celery_workers, worker_backend

    with patch.dict("os.environ", {"WORKER_BACKEND": "celery"}, clear=False):
        assert worker_backend() == "celery"
        assert use_celery_workers() is True


def test_worker_backend_thread_legacy():
    from services.workers.runtime import use_thread_workers, worker_backend

    with patch.dict("os.environ", {"WORKER_BACKEND": "thread"}, clear=False):
        assert worker_backend() == "thread"
        assert use_thread_workers() is True


def test_celery_mode_skips_thread_start():
    from services.workers.publish_worker import _THREAD, start_background_worker

    with patch.dict(
        "os.environ",
        {"WORKER_BACKEND": "celery", "PUBLISH_QUEUE_ENABLED": "1"},
        clear=False,
    ):
        started = start_background_worker()
        assert started is True
        assert _THREAD is None or not _THREAD.is_alive()


def test_thread_mode_starts_daemon_thread():
    import services.workers.publish_worker as mod

    with patch.dict(
        "os.environ",
        {"WORKER_BACKEND": "thread", "PUBLISH_QUEUE_ENABLED": "1", "WORKER_LEADER_LOCK_ENABLED": "0"},
        clear=False,
    ):
        mod._STOP.set()
        if mod._THREAD and mod._THREAD.is_alive():
            mod.stop_background_worker()
        mod._THREAD = None
        started = mod.start_background_worker()
        assert started is True
        assert mod._THREAD is not None
        assert mod._THREAD.is_alive()
        mod.stop_background_worker()


def test_worker_status_active_in_celery_mode():
    from services.workers.publish_worker import get_worker_status

    with patch.dict(
        "os.environ",
        {"WORKER_BACKEND": "celery", "PUBLISH_QUEUE_ENABLED": "1"},
        clear=False,
    ):
        with patch("infra.worker_health.celery_worker_online", return_value=True):
            status = get_worker_status()
        assert status["worker_backend"] == "celery"
        assert status["active"] is True
        assert status["thread_alive"] is False


def test_beat_schedule_respects_enabled_flags():
    from infra.celery_schedule import build_beat_schedule

    with patch.dict(
        "os.environ",
        {
            "PUBLISH_QUEUE_ENABLED": "1",
            "AD_POLL_ENABLED": "0",
            "ROI_ALERT_CLEANUP_ENABLED": "1",
            "POST_PUBLISH_MONITOR_ENABLED": "1",
        },
        clear=False,
    ):
        schedule = build_beat_schedule()
        assert "publish-queue" in schedule
        assert "ad-report-poller" not in schedule
        assert "alert-cleanup-scheduler" in schedule
        assert "task-cleanup" in schedule


def test_celery_tasks_registered():
    from infra.task_queue import celery_app

    names = {
        "commerce_agent.tasks.publish_queue_tick",
        "commerce_agent.tasks.ad_poll_tick",
        "commerce_agent.tasks.roi_report_tick",
        "commerce_agent.tasks.alert_cleanup_tick",
        "commerce_agent.tasks.perception_tick",
        "commerce_agent.tasks.post_publish_monitor_tick",
        "commerce_agent.tasks.task_cleanup_tick",
        "commerce_agent.health_check",
    }
    registered = set(celery_app.tasks.keys())
    assert names.issubset(registered)


def test_readiness_celery_requires_redis_not_leader_lock():
    import asyncio

    from infra.readiness import check_readiness

    with patch.dict("os.environ", {"WORKER_BACKEND": "celery"}, clear=False):
        result = asyncio.run(check_readiness())
        assert result["worker_backend"] == "celery"
        assert result["leader_lock_required"] is False
        assert result["redis_required"] is True
