"""Phase 3: 可观测性与 readiness 测试。"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


def test_readiness_sqlite_only():
    from infra.readiness import check_readiness

    with patch.dict(
        "os.environ",
        {"WORKER_BACKEND": "thread", "WORKER_LEADER_LOCK_ENABLED": "0"},
        clear=False,
    ):
        import asyncio

        result = asyncio.run(check_readiness())
    assert result["ok"] is True
    assert any(c["service"] == "sqlite" for c in result["checks"])


def test_health_ready_endpoint():
    from fastapi.testclient import TestClient

    from api_server import app

    with patch.dict(
        "os.environ",
        {"WORKER_BACKEND": "thread", "WORKER_LEADER_LOCK_ENABLED": "0"},
        clear=False,
    ):
        client = TestClient(app)
        r = client.get("/api/health/ready")
    assert r.status_code == 200
    assert r.json().get("ready") is True


def test_metrics_endpoint_has_counters():
    from fastapi.testclient import TestClient

    from api_server import app

    client = TestClient(app)
    client.get("/api/health")
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert "commerce_agent_requests_total" in body


def test_infra_health_updates_gauge():
    from infra.health import check_all
    from infra.metrics import INFRA_HEALTH

    import asyncio

    with patch.dict("os.environ", {"WORKER_LEADER_LOCK_ENABLED": "0"}, clear=False):
        asyncio.run(check_all(include_worker=False))
    samples = INFRA_HEALTH.collect()[0].samples
    assert samples
