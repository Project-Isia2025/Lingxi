"""API 鉴权中间件测试。"""
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


def test_auth_disabled_allows_api(client):
    with patch.dict("os.environ", {"API_AUTH_ENABLED": "0"}, clear=False):
        r = client.get("/api/orchestrator/status")
    assert r.status_code == 200


def test_auth_enabled_blocks_without_key(client):
    with patch.dict(
        "os.environ",
        {"API_AUTH_ENABLED": "1", "API_AUTH_KEY": "test-secret-key-12345"},
        clear=False,
    ):
        r = client.get("/api/orchestrator/status")
    assert r.status_code == 401
    assert r.json().get("error") == "unauthorized"


def test_auth_enabled_accepts_header(client):
    with patch.dict(
        "os.environ",
        {"API_AUTH_ENABLED": "1", "API_AUTH_KEY": "test-secret-key-12345"},
        clear=False,
    ):
        r = client.get("/api/orchestrator/status", headers={"X-API-Key": "test-secret-key-12345"})
    assert r.status_code == 200


def test_auth_login_sets_cookie(client):
    with patch.dict(
        "os.environ",
        {"API_AUTH_ENABLED": "1", "API_AUTH_KEY": "test-secret-key-12345"},
        clear=False,
    ):
        r = client.post("/api/auth/login", json={"api_key": "test-secret-key-12345"})
    assert r.status_code == 200
    assert r.json().get("ok") is True
    assert "matrix_api_key" in (r.headers.get("set-cookie") or "").lower()


def test_auth_cookie_allows_read_api(client):
    with patch.dict(
        "os.environ",
        {"API_AUTH_ENABLED": "1", "API_AUTH_KEY": "test-secret-key-12345"},
        clear=False,
    ):
        login = client.post("/api/auth/login", json={"api_key": "test-secret-key-12345"})
        assert login.status_code == 200
        r = client.get("/api/orchestrator/status")
    assert r.status_code == 200


def test_public_health_without_key(client):
    with patch.dict(
        "os.environ",
        {"API_AUTH_ENABLED": "1", "API_AUTH_KEY": "test-secret-key-12345"},
        clear=False,
    ):
        r = client.get("/api/health")
    assert r.status_code == 200


def test_rpa_webhook_public_without_api_key(client):
    with patch.dict(
        "os.environ",
        {"API_AUTH_ENABLED": "1", "API_AUTH_KEY": "test-secret-key-12345", "RPA_WEBHOOK_SECRET": ""},
        clear=False,
    ):
        r = client.post(
            "/api/rpa/webhook/yingdao",
            json={"platform": "douyin", "keyword": "auth-test", "items": []},
        )
    assert r.status_code == 200
