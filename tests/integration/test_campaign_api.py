"""Phase 7 Campaign API 集成测试。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


@pytest.fixture
def client():
    from api.routes import app

    return TestClient(app)


def test_start_campaign_sync(client):
    resp = client.post(
        "/campaigns/start",
        json={
            "goal": "集成测试带货",
            "platform": "douyin",
            "budget": 100,
            "max_iterations": 1,
            "sync": True,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["campaign_id"]
    assert body["status"] in ("completed", "optimizing", "executed")

    status = client.get(f"/campaigns/{body['campaign_id']}/status")
    assert status.status_code == 200
    sbody = status.json()
    assert sbody["iteration"] is not None and sbody["iteration"] > 0


def test_campaign_not_found(client):
    resp = client.get("/campaigns/nonexistent-id/status")
    assert resp.status_code == 404
