"""Phase 7 Campaign API 单元测试。"""
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


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("healthy", "degraded")
    assert body["service"] == "content-commerce-agent"


def test_schemas_import():
    from api.schemas import CampaignRequest, CampaignResponse, CampaignStatusResponse, HealthResponse

    req = CampaignRequest(goal="测试")
    assert req.platform == "douyin"
    assert CampaignResponse(status="started", campaign_id="x")
    assert HealthResponse(status="healthy")


def test_campaign_store_crud():
    from api.campaign_store import create, get, update

    cid = "test-campaign-001"
    create(cid, goal="g", platform="douyin", budget=100)
    row = get(cid)
    assert row and row["status"] == "started"
    update(cid, status="completed", state={"current_roi": 1.5})
    assert get(cid)["state"]["current_roi"] == 1.5
