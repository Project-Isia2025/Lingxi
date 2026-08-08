"""API 鉴权分级策略测试。"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


@pytest.fixture
def client():
    from api_server import app

    return TestClient(app)


_AUTH_ENV = {
    "API_AUTH_ENABLED": "1",
    "API_AUTH_KEY": "test-secret-key-12345",
    "API_AUTH_ADMIN_KEY": "test-admin-key-678901234",
}


def test_resolve_tier_public_health():
    from api.auth_policy import AuthTier, resolve_auth_tier

    assert resolve_auth_tier("GET", "/api/health") == AuthTier.PUBLIC
    assert resolve_auth_tier("GET", "/api/health/ready") == AuthTier.PUBLIC


def test_resolve_tier_webhook_and_review():
    from api.auth_policy import AuthTier, resolve_auth_tier

    assert resolve_auth_tier("POST", "/api/rpa/webhook/yingdao") == AuthTier.WEBHOOK
    assert resolve_auth_tier("POST", "/api/review/callback") == AuthTier.WEBHOOK
    assert resolve_auth_tier("GET", "/api/review/abc123/approve") == AuthTier.REVIEW
    assert resolve_auth_tier("POST", "/api/review/abc123/reject") == AuthTier.REVIEW


def test_resolve_tier_read_write_admin():
    from api.auth_policy import AuthTier, resolve_auth_tier

    assert resolve_auth_tier("GET", "/api/orchestrator/status") == AuthTier.READ
    assert resolve_auth_tier("POST", "/api/perception/scan") == AuthTier.WRITE
    assert resolve_auth_tier("POST", "/api/orchestrator/run") == AuthTier.ADMIN
    assert resolve_auth_tier("POST", "/api/publish/run") == AuthTier.ADMIN


def test_auth_disabled_allows_api(client):
    with patch.dict("os.environ", {"API_AUTH_ENABLED": "0"}, clear=False):
        r = client.get("/api/orchestrator/status")
    assert r.status_code == 200


def test_read_tier_blocks_without_key(client):
    with patch.dict("os.environ", _AUTH_ENV, clear=False):
        r = client.get("/api/orchestrator/status")
    assert r.status_code == 401
    assert r.json().get("tier") == "read"


def test_read_tier_accepts_standard_key(client):
    with patch.dict("os.environ", _AUTH_ENV, clear=False):
        r = client.get("/api/orchestrator/status", headers={"X-API-Key": _AUTH_ENV["API_AUTH_KEY"]})
    assert r.status_code == 200


def test_admin_tier_rejects_standard_key_when_admin_configured(client):
    with patch.dict("os.environ", _AUTH_ENV, clear=False):
        r = client.post(
            "/api/orchestrator/run",
            json={"keyword": "护肤", "platform": "xhs", "sync": True},
            headers={"X-API-Key": _AUTH_ENV["API_AUTH_KEY"]},
        )
    assert r.status_code == 403
    assert r.json().get("tier") == "admin"


def test_admin_tier_accepts_admin_key(client):
    with patch.dict("os.environ", _AUTH_ENV, clear=False):
        r = client.post(
            "/api/orchestrator/run",
            json={"keyword": "护肤", "platform": "xhs", "sync": True},
            headers={"X-API-Key": _AUTH_ENV["API_AUTH_ADMIN_KEY"]},
        )
    assert r.status_code != 401
    assert r.status_code != 403


def test_admin_tier_falls_back_to_standard_key_without_admin_env(client):
    env = {"API_AUTH_ENABLED": "1", "API_AUTH_KEY": "test-secret-key-12345"}
    with patch.dict("os.environ", env, clear=False):
        r = client.post(
            "/api/orchestrator/run",
            json={"keyword": "护肤", "platform": "xhs", "sync": True},
            headers={"X-API-Key": env["API_AUTH_KEY"]},
        )
    assert r.status_code != 401
    assert r.status_code != 403


def test_public_health_without_key(client):
    with patch.dict("os.environ", _AUTH_ENV, clear=False):
        r = client.get("/api/health")
    assert r.status_code == 200


def test_dashboard_html_public_without_key(client):
    with patch.dict("os.environ", _AUTH_ENV, clear=False):
        r = client.get("/dashboard")
    assert r.status_code == 200


def test_rpa_webhook_public_without_api_key(client):
    with patch.dict(
        "os.environ",
        {**_AUTH_ENV, "RPA_WEBHOOK_SECRET": ""},
        clear=False,
    ):
        r = client.post(
            "/api/rpa/webhook/yingdao",
            json={"platform": "douyin", "keyword": "auth-test", "items": []},
        )
    assert r.status_code == 200


def test_auth_login_sets_cookie(client):
    with patch.dict("os.environ", _AUTH_ENV, clear=False):
        r = client.post("/api/auth/login", json={"api_key": _AUTH_ENV["API_AUTH_KEY"]})
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_auth_policy_endpoint(client):
    with patch.dict("os.environ", _AUTH_ENV, clear=False):
        r = client.get("/api/auth/policy", params={"method": "POST", "path": "/api/publish/run"})
    assert r.status_code == 200
    body = r.json()
    assert body["example"]["tier"] == "admin"
    assert body["rule_count"] > 0
