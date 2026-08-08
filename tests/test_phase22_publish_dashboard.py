"""Phase22：发布队列 Dashboard + 矩阵错峰限流。"""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


class PublishRateLimitTest(unittest.TestCase):
    def test_stagger_same_run(self) -> None:
        from services.publish_rate_limit import resolve_scheduled_ts

        now = int(time.time())
        queued = [
            {"platform": "douyin", "account_id": "a1", "run_id": "run-x", "status": "queued", "scheduled_ts": now},
            {"platform": "douyin", "account_id": "a1", "run_id": "run-x", "status": "queued", "scheduled_ts": now + 120},
        ]
        with patch.dict("os.environ", {"PUBLISH_RATE_LIMIT_ENABLED": "1", "MATRIX_RUN_STAGGER_SEC": "120"}), patch(
            "core.storage.list_publish_queue_items",
            return_value=queued,
        ):
            out = resolve_scheduled_ts(platform="douyin", account_id="a1", run_id="run-x")
        self.assertTrue(out.get("ok"))
        self.assertGreaterEqual(int(out["scheduled_ts"]), now + 200)

    def test_run_queue_limit(self) -> None:
        from services.publish_rate_limit import resolve_scheduled_ts

        queued = [
            {"platform": "douyin", "account_id": "a1", "run_id": "run-full", "status": "queued", "scheduled_ts": 1}
            for _ in range(12)
        ]
        with patch.dict("os.environ", {"PUBLISH_MAX_QUEUED_PER_RUN": "12"}), patch(
            "core.storage.list_publish_queue_items",
            return_value=queued,
        ):
            out = resolve_scheduled_ts(platform="douyin", account_id="a1", run_id="run-full")
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "run_queue_limit")


class SchedulePublishRateLimitTest(unittest.TestCase):
    def test_schedule_publish_applies_rate_limit(self) -> None:
        from services.publish.scheduler import schedule_publish

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "pq.db"
            with patch("core.storage.DB_PATH", db), patch(
                "services.publish_rate_limit.resolve_scheduled_ts",
                return_value={"ok": True, "scheduled_ts": int(time.time()) + 600, "rate_limited": True},
            ), patch("services.publish.scheduler.sync_accounts_to_db", return_value=0), patch(
                "services.publish.scheduler.pick_publish_account",
                return_value="default",
            ):
                from core.storage import init_storage

                init_storage()
                out = schedule_publish(
                    platform="douyin",
                    video_path="v.mp4",
                    script="测试",
                    run_id="run-sched",
                )
            self.assertTrue(out.get("ok"))
            self.assertTrue((out.get("rate_limit") or {}).get("rate_limited"))


class PublishQueueDashboardTest(unittest.TestCase):
    def test_build_dashboard(self) -> None:
        from services.publish_queue_dashboard import build_publish_queue_dashboard

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "dash.db"
            with patch("core.storage.DB_PATH", db), patch(
                "services.publish_worker.get_worker_status",
                return_value={"enabled": True, "pending_queued": 2, "batch_size": 5},
            ):
                from core.storage import init_storage, enqueue_publish

                init_storage()
                jid = str(uuid.uuid4())
                enqueue_publish(
                    job_id=jid,
                    platform="douyin",
                    account_id="default",
                    video_path="a.mp4",
                    script="脚本",
                    title="标题",
                    run_id="run-dash",
                    scheduled_ts=int(time.time()) + 100,
                    priority=8,
                )
                out = build_publish_queue_dashboard(limit=20)
            self.assertTrue(out.get("ok"))
            self.assertGreaterEqual(out["stats"]["total"], 1)
            self.assertIn("rate_limit", out)


if __name__ == "__main__":
    unittest.main()
