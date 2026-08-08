"""Phase 2: settings / leader lock / storage / routing 测试。"""
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


def test_settings_production_validation():
    from config.settings import Settings

    s = Settings(environment="production", api_auth_enabled=False, api_auth_key="")
    errors = s.validate_production()
    assert any("API_AUTH" in e for e in errors)
    assert any("RPA_WEBHOOK" in e for e in errors)


def test_leader_lock_disabled_always_leader():
    from infra.leader_lock import try_acquire_leader

    with patch.dict("os.environ", {"WORKER_LEADER_LOCK_ENABLED": "0"}, clear=False):
        assert try_acquire_leader("test-lock") is True


def test_core_db_init_and_kb():
    from core.db import DB_PATH, init_storage
    from core.storage import kb_search, kb_upsert

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        with patch("core.db.DB_PATH", db), patch("core.storage.DB_PATH", db):
            init_storage()
            kid = kb_upsert(library="faq", title="测试条目", body="内容", tags="test")
            assert kid > 0
            hits = kb_search(query="测试", library="faq", limit=3)
            assert hits


def test_orchestrator_routing_info():
    from orchestrator.routing import orchestrator_routing_info

    info = orchestrator_routing_info()
    assert info["production_path"] == "orchestrator_agent"
    assert info["experimental_path"] == "langgraph"


def test_langgraph_run_disabled_by_default():
    from fastapi.testclient import TestClient

    from api_server import app

    with patch.dict("os.environ", {"LANGGRAPH_ORCHESTRATOR_ENABLED": "0"}, clear=False):
        client = TestClient(app)
        r = client.post("/api/orchestrator/langgraph/run", json={"goal": "测试", "platform": "douyin"})
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "langgraph_disabled"


def test_orchestrator_routing_endpoint():
    from fastapi.testclient import TestClient

    from api_server import app

    client = TestClient(app)
    r = client.get("/api/orchestrator/routing")
    assert r.status_code == 200
    body = r.json()
    assert body["production_path"] == "orchestrator_agent"
