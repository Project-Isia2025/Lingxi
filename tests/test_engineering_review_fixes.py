"""工程审查修复相关测试。"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


def test_sqlite_wal_enabled():
    from core.db import connect

    conn = connect()
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert str(mode).lower() == "wal"


def test_production_cors_validation():
    from config.settings import Settings

    s = Settings(
        environment="production",
        api_auth_enabled=True,
        api_auth_key="x" * 20,
        review_token_secret="strong-secret-value",
        rpa_webhook_secret="rpa-secret",
        cors_origins="",
    )
    errors = s.validate_production()
    assert any("CORS" in e for e in errors)


def test_production_docs_require_auth():
    from api.auth_policy import AuthTier, resolve_auth_tier

    with patch.dict(
        "os.environ",
        {"ENVIRONMENT": "production", "API_AUTH_ENABLED": "1", "DOCS_PUBLIC_IN_PRODUCTION": "0"},
        clear=False,
    ):
        assert resolve_auth_tier("GET", "/docs") == AuthTier.READ
        assert resolve_auth_tier("GET", "/metrics") == AuthTier.READ


def test_rpa_webhook_denied_in_production_without_secret():
    from services.rpa_ingest import verify_webhook_token

    with patch.dict("os.environ", {"ENVIRONMENT": "production", "RPA_WEBHOOK_SECRET": ""}, clear=False):
        out = verify_webhook_token("")
        assert out["ok"] is False


def test_rpa_webhook_open_in_development():
    from services.rpa_ingest import verify_webhook_token

    with patch.dict("os.environ", {"ENVIRONMENT": "development", "RPA_WEBHOOK_SECRET": ""}, clear=False):
        out = verify_webhook_token("")
        assert out["ok"] is True


def test_query_api_key_disabled_in_production():
    from api.auth import extract_api_key

    class Req:
        query_params = {"api_key": "secret-from-query"}
        headers = {}
        cookies = {}

    with patch.dict(
        "os.environ",
        {"ENVIRONMENT": "production", "API_AUTH_ALLOW_QUERY_KEY": "0"},
        clear=False,
    ):
        assert extract_api_key(Req()) == ""


def test_celery_worker_required_in_readiness():
    import asyncio

    from infra.readiness import check_readiness

    with patch.dict(
        "os.environ",
        {"WORKER_BACKEND": "celery", "PUBLISH_QUEUE_ENABLED": "1"},
        clear=False,
    ):
        with patch("infra.worker_health.celery_worker_online", return_value=False):
            result = asyncio.run(check_readiness())
        assert result["celery_worker_required"] is True
        assert result["ok"] is False
