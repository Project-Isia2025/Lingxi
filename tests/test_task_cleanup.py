"""历史任务删除与自动清理测试。"""
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


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "task_cleanup.db"
        with patch("core.db.DB_PATH", db), patch("core.storage.DB_PATH", db):
            from core.db import init_storage

            init_storage()
            yield db


def test_delete_review_pending(temp_db):
    from core.storage import enqueue_review, get_review_item
    from services.review_queue import delete_review_item

    enqueue_review(
        review_id="rev-test-1",
        run_id="run-1",
        video_path="/tmp/a.mp4",
        script="test",
        title="测试",
    )
    assert get_review_item("rev-test-1") is not None
    out = delete_review_item("rev-test-1")
    assert out["ok"] is True
    assert get_review_item("rev-test-1") is None


def test_auto_delete_on_approve(temp_db):
    from core.storage import enqueue_review, get_review_item
    from services.feishu_review import review_token
    from services.review_queue import approve_review

    rid = "rev-auto-del"
    enqueue_review(
        review_id=rid,
        run_id="run-ex-review",
        video_path="/tmp/a.mp4",
        script="测试口播",
        title="A面膜",
    )
    with patch.dict("os.environ", {"REVIEW_AUTO_DELETE_ON_RESOLVE": "1"}, clear=False):
        with patch("services.review_queue.schedule_publish", create=True):
            with patch("services.publish.scheduler.schedule_publish", return_value={"ok": True}):
                out = approve_review(review_id=rid, token=review_token(rid))
    assert out["ok"] is True
    assert get_review_item(rid) is None


def test_purge_completed_run(temp_db):
    from orchestrator.workflow_store import delete_run, list_runs, save_run

    save_run(
        {
            "run_id": "run-done-1",
            "status": "completed",
            "stage": "done",
            "goal": {"keyword": "测试"},
        }
    )
    assert any(r["run_id"] == "run-done-1" for r in list_runs(limit=10))
    assert delete_run("run-done-1") is True
    assert not any(r["run_id"] == "run-done-1" for r in list_runs(limit=10))


def test_workflow_delete_run_api(temp_db):
    from fastapi.testclient import TestClient

    from api_server import app
    from orchestrator.workflow_store import save_run

    save_run(
        {
            "run_id": "run-del-api",
            "status": "completed",
            "stage": "done",
            "goal": {"keyword": "测试"},
        }
    )
    client = TestClient(app)
    r = client.delete("/api/workflow/runs/run-del-api")
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_workflow_clear_pending_api(temp_db):
    from fastapi.testclient import TestClient

    from api_server import app
    from core.storage import enqueue_review, list_review_queue

    enqueue_review(
        review_id="rev-clear-a",
        run_id="run-ex-review",
        video_path="/tmp/a.mp4",
        script="测试",
        title="A面膜",
    )
    enqueue_review(
        review_id="rev-clear-b",
        run_id="run-ex-review",
        video_path="/tmp/b.mp4",
        script="测试",
        title="A面膜",
    )
    assert len(list_review_queue(status="pending_review", limit=50)) >= 2
    client = TestClient(app)
    r = client.post("/api/workflow/decisions/clear-pending")
    assert r.status_code == 200
    assert r.json().get("deleted", 0) >= 2
    assert len(list_review_queue(status="pending_review", limit=50)) == 0


def test_clear_all_completed_runs(temp_db):
    from orchestrator.workflow_store import list_runs, save_run
    from services.task_cleanup import clear_all_completed_runs

    save_run({"run_id": "run-c1", "status": "completed", "stage": "done", "goal": {"keyword": "护肤"}})
    save_run({"run_id": "run-c2", "status": "cancelled", "stage": "done", "goal": {"keyword": "护肤"}})
    assert len(list_runs(limit=20)) >= 2
    out = clear_all_completed_runs()
    assert out["deleted"] >= 2
    assert out["after_count"] == 0


def test_workflow_clear_completed_api(temp_db):
    from fastapi.testclient import TestClient

    from api_server import app
    from orchestrator.workflow_store import save_run

    save_run({"run_id": "run-api-clear", "status": "completed", "stage": "done", "goal": {"keyword": "护肤"}})
    client = TestClient(app)
    r = client.post("/api/workflow/runs/clear-completed")
    assert r.status_code == 200
    assert r.json().get("deleted", 0) >= 1


def test_workflow_delete_decision_api(temp_db):
    from fastapi.testclient import TestClient

    from api_server import app
    from core.storage import enqueue_review

    enqueue_review(
        review_id="rev-ui-remove",
        run_id="run-ex-review",
        video_path="/tmp/a.mp4",
        script="测试",
        title="A面膜",
    )
    client = TestClient(app)
    r = client.delete("/api/workflow/decisions/rev-ui-remove")
    assert r.status_code == 200
    assert r.json().get("ok") is True
