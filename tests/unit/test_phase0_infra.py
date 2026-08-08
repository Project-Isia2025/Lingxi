"""Phase 0 基础设施单元测试。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


def test_infra_modules_exist():
    from infra.database import Base, SessionLocal, database_url, engine
    from infra.health import check_all, check_celery_broker
    from infra.message_bus import MessageBus
    from infra.metrics import render_metrics
    from infra.object_storage import ObjectStorage
    from infra.redis_client import redis_client
    from infra.task_queue import celery_app, health_check

    assert Base is not None
    assert "postgresql" in database_url()
    assert engine is not None
    assert SessionLocal is not None
    assert redis_client is not None
    assert MessageBus is not None
    assert celery_app.main == "commerce_agent"
    assert callable(health_check)
    assert ObjectStorage is not None
    assert callable(check_all)
    assert callable(check_celery_broker)
    body, ctype = render_metrics()
    assert b"commerce_agent" in body
    assert "text" in ctype


def test_docker_compose_infra_file():
    text = (ROOT / "docker-compose.infra.yml").read_text(encoding="utf-8")
    for svc in ("postgres", "redis", "qdrant", "minio", "prometheus", "grafana", "celery-worker"):
        assert svc in text


def test_message_bus_publish_interface():
    import inspect

    from infra.message_bus import MessageBus

    assert inspect.iscoroutinefunction(MessageBus.publish)


@pytest.mark.asyncio
async def test_health_check_all_runs():
    from infra.health import check_all

    report = await check_all(include_worker=False)
    assert "checks" in report
    assert len(report["checks"]) >= 5
