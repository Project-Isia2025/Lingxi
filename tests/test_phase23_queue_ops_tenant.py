"""Phase23：队列优先级手动调整 + org_id 多租户隔离。"""
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


class PublishQueueOpsTest(unittest.TestCase):
    def test_set_and_bump_priority(self) -> None:
        from core.storage import enqueue_publish, init_storage
        from services.publish_queue_ops import bump_job_priority, set_job_priority

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "ops.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()
                jid = str(uuid.uuid4())
                enqueue_publish(
                    job_id=jid,
                    platform="douyin",
                    account_id="default",
                    video_path="a.mp4",
                    script="s",
                    priority=3,
                )
                out = set_job_priority(job_id=jid, priority=12)
                self.assertTrue(out.get("ok"))
                bumped = bump_job_priority(job_id=jid, delta=3)
                self.assertTrue(bumped.get("ok"))
                self.assertEqual(bumped.get("priority"), 15)

    def test_cancel_job(self) -> None:
        from core.storage import enqueue_publish, get_publish_queue_job, init_storage
        from services.publish_queue_ops import cancel_queued_job

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "c.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()
                jid = str(uuid.uuid4())
                enqueue_publish(
                    job_id=jid,
                    platform="douyin",
                    account_id="default",
                    video_path="a.mp4",
                    script="s",
                )
                out = cancel_queued_job(job_id=jid, reason="test")
                self.assertTrue(out.get("ok"))
                job = get_publish_queue_job(jid)
                self.assertEqual(job.get("status"), "cancelled")


class OrgIsolationTest(unittest.TestCase):
    def test_filter_by_org(self) -> None:
        from services.tenant import filter_by_org

        items = [
            {"job_id": "1", "payload": {"org_id": "shop-a"}},
            {"job_id": "2", "payload": {"org_id": "shop-b"}},
            {"job_id": "3", "payload": {}},
        ]
        with patch.dict("os.environ", {"ORG_ISOLATION_ENABLED": "1"}):
            out = filter_by_org(items, "shop-a")
        ids = [x["job_id"] for x in out]
        self.assertIn("1", ids)
        self.assertIn("3", ids)
        self.assertNotIn("2", ids)

    def test_enqueue_with_org_id(self) -> None:
        from core.storage import enqueue_publish, init_storage, list_publish_queue_items

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "org.db"
            with patch("core.storage.DB_PATH", db), patch.dict("os.environ", {"ORG_ISOLATION_ENABLED": "1"}):
                init_storage()
                enqueue_publish(
                    job_id=str(uuid.uuid4()),
                    platform="douyin",
                    account_id="default",
                    video_path="a.mp4",
                    script="s",
                    org_id="brand-x",
                )
                all_items = list_publish_queue_items(limit=10)
                filtered = list_publish_queue_items(limit=10, org_id="brand-x")
                self.assertEqual(len(all_items), 1)
                self.assertEqual(len(filtered), 1)
                self.assertEqual(filtered[0].get("org_id"), "brand-x")

    def test_org_access_denied(self) -> None:
        from core.storage import enqueue_publish, init_storage
        from services.publish_queue_ops import set_job_priority

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "deny.db"
            with patch("core.storage.DB_PATH", db), patch.dict("os.environ", {"ORG_ISOLATION_ENABLED": "1"}):
                init_storage()
                jid = str(uuid.uuid4())
                enqueue_publish(
                    job_id=jid,
                    platform="douyin",
                    account_id="default",
                    video_path="a.mp4",
                    script="s",
                    org_id="tenant-a",
                )
                out = set_job_priority(job_id=jid, priority=10, org_id="tenant-b")
                self.assertFalse(out.get("ok"))
                self.assertEqual(out.get("error"), "org_access_denied")


if __name__ == "__main__":
    unittest.main()
