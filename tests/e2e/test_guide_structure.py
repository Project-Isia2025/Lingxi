"""Phase 0-7 基础设施与模块存在性测试。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


def test_infra_modules_import():
    from infra.database import Base, SessionLocal, engine
    from infra.redis_client import MessageBus, redis_client
    from infra.task_queue import celery_app
    from infra.object_storage import ObjectStorage

    assert Base is not None
    assert SessionLocal is not None
    assert engine is not None
    assert redis_client is not None
    assert MessageBus is not None
    assert celery_app.main == "commerce_agent"
    assert ObjectStorage is not None


def test_docker_compose_has_infra_services():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for svc in ("postgres", "redis", "qdrant", "minio", "prometheus", "grafana"):
        assert svc in compose


def test_project_structure():
    required = [
        "orchestrator/graph.py",
        "orchestrator/state.py",
        "orchestrator/nodes.py",
        "orchestrator/roi_monitor.py",
        "agents/base.py",
        "agents/perception/scraper.py",
        "agents/strategy/product_selector.py",
        "agents/content/script_generator.py",
        "agents/execution/publisher.py",
        "memory/vector_store.py",
        "memory/banned_words.py",
        "infra/database.py",
        "api/routes.py",
        "api/schemas.py",
        "deploy/prometheus.yml",
        "deploy/sql/init.sql",
        "pyproject.toml",
        ".env.example",
    ]
    for p in required:
        assert (ROOT / p).is_file(), f"missing: {p}"
