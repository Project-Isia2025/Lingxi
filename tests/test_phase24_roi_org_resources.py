"""Phase24：ROI 驱动队列优先级自动刷新 + 多 org 账号/库存配置。"""
from __future__ import annotations

import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


class RoiPriorityRefreshTest(unittest.TestCase):
    def test_refresh_skips_manual_priority(self) -> None:
        from core.storage import enqueue_publish, get_publish_queue_job, init_storage
        from services.publish_priority import refresh_queue_priorities

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "roi.db"
            with patch("core.storage.DB_PATH", db), patch.dict(
                "os.environ",
                {"PUBLISH_DYNAMIC_PRIORITY": "1"},
            ), patch(
                "services.publish_priority.get_run_priority_context",
                return_value={
                    "run_id": "run-a",
                    "combined_roi_score": 0.8,
                    "grade": "A",
                    "suggested_priority": 15,
                    "mode": "computed",
                },
            ):
                init_storage()
                jid = str(uuid.uuid4())
                enqueue_publish(
                    job_id=jid,
                    platform="douyin",
                    account_id="default",
                    video_path="a.mp4",
                    script="s",
                    run_id="run-a",
                    priority=5,
                )
                from core.storage import update_publish_queue_priority

                update_publish_queue_priority(jid, 8, source="manual")
                out = refresh_queue_priorities(limit=10)
                self.assertTrue(out.get("ok"))
                self.assertEqual(out.get("skipped_locked"), 1)
                self.assertEqual(out.get("updated"), 0)
                job = get_publish_queue_job(jid)
                self.assertEqual(int(job.get("priority") or 0), 8)

    def test_refresh_updates_by_roi(self) -> None:
        from core.storage import enqueue_publish, get_publish_queue_job, init_storage
        from services.publish_priority import refresh_queue_priorities

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "roi2.db"
            with patch("core.storage.DB_PATH", db), patch.dict(
                "os.environ",
                {"PUBLISH_DYNAMIC_PRIORITY": "1"},
            ), patch(
                "services.publish_priority.get_run_priority_context",
                return_value={
                    "run_id": "run-b",
                    "combined_roi_score": 0.62,
                    "grade": "B",
                    "suggested_priority": 10,
                    "mode": "computed",
                },
            ):
                init_storage()
                jid = str(uuid.uuid4())
                enqueue_publish(
                    job_id=jid,
                    platform="douyin",
                    account_id="default",
                    video_path="a.mp4",
                    script="s",
                    run_id="run-b",
                    priority=3,
                )
                out = refresh_queue_priorities(limit=10)
                self.assertTrue(out.get("ok"))
                self.assertEqual(out.get("updated"), 1)
                detail = (out.get("details") or [])[0]
                self.assertEqual(detail.get("old"), 3)
                self.assertEqual(detail.get("new"), 10)
                job = get_publish_queue_job(jid)
                self.assertEqual(int(job.get("priority") or 0), 10)
                self.assertEqual(float(job["payload"]["combined_roi_score"]), 0.62)

    def test_combined_roi_triggers_run_refresh(self) -> None:
        from services.combined_roi import apply_combined_roi_for_run

        with patch.dict("os.environ", {"COMBINED_ROI_ENABLED": "1", "PUBLISH_ROI_AUTO_REFRESH": "1"}), patch(
            "services.combined_roi.resolve_run_roi_inputs",
            return_value=(0.7, 0.6),
        ), patch(
            "services.combined_roi.metrics_record",
        ), patch(
            "services.combined_roi.kb_upsert",
        ), patch(
            "services.combined_roi.save_episodic",
        ), patch(
            "services.publish_priority.refresh_priorities_for_run",
            return_value={"ok": True, "updated": 2},
        ) as mock_refresh:
            out = apply_combined_roi_for_run("run-c", keyword="面膜")
        self.assertTrue(out.get("ok"))
        mock_refresh.assert_called_once_with("run-c")
        self.assertEqual((out.get("priority_refresh") or {}).get("updated"), 2)


class OrgResourcesTest(unittest.TestCase):
    def test_filter_accounts_by_org(self) -> None:
        from services.org_resources import filter_accounts_by_org

        rows = [
            {"account_id": "a1", "org_id": "brand-a"},
            {"account_id": "a2", "org_id": "brand-b"},
            {"account_id": "a3"},
        ]
        with patch.dict("os.environ", {"ORG_ISOLATION_ENABLED": "1"}):
            out = filter_accounts_by_org(rows, "brand-a")
        ids = [x["account_id"] for x in out]
        self.assertIn("a1", ids)
        self.assertIn("a3", ids)
        self.assertNotIn("a2", ids)

    def test_list_accounts_for_org(self) -> None:
        from services.publish.scheduler import list_accounts

        sample = [
            {"account_id": "dy-a", "platform": "douyin", "enabled": True, "org_id": "brand-a"},
            {"account_id": "dy-b", "platform": "douyin", "enabled": True, "org_id": "brand-b"},
        ]
        with patch("services.publish.scheduler.load_accounts_file", return_value=sample), patch.dict(
            "os.environ",
            {"ORG_ISOLATION_ENABLED": "1"},
        ):
            out = list_accounts(platform="douyin", org_id="brand-a")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["account_id"], "dy-a")

    def test_inventory_filter_by_org(self) -> None:
        from services.inventory import list_products

        sample = [
            {"sku": "A", "stock": 10, "enabled": True, "priority": 1, "org_id": "shop-a"},
            {"sku": "B", "stock": 10, "enabled": True, "priority": 1, "org_id": "shop-b"},
        ]
        with patch("services.inventory.load_inventory", return_value=sample), patch.dict(
            "os.environ",
            {"ORG_ISOLATION_ENABLED": "1"},
        ):
            out = list_products(org_id="shop-a")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["sku"], "A")

    def test_dashboard_enriches_roi_fields(self) -> None:
        from services.publish_queue_dashboard import build_publish_queue_dashboard

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "dash24.db"
            with patch("core.storage.DB_PATH", db), patch(
                "services.publish_worker.get_worker_status",
                return_value={"enabled": False, "pending_queued": 0, "batch_size": 5},
            ), patch(
                "services.publish_priority.get_run_priority_context",
                return_value={
                    "combined_roi_score": 0.78,
                    "grade": "A",
                    "suggested_priority": 15,
                },
            ):
                from core.storage import enqueue_publish, init_storage

                init_storage()
                enqueue_publish(
                    job_id=str(uuid.uuid4()),
                    platform="douyin",
                    account_id="default",
                    video_path="a.mp4",
                    script="s",
                    run_id="run-dash",
                    priority=5,
                )
                out = build_publish_queue_dashboard(limit=20)
            self.assertTrue(out.get("ok"))
            item = out["items"][0]
            self.assertEqual(item.get("roi_grade"), "A")
            self.assertEqual(item.get("suggested_priority"), 15)
            self.assertEqual(item.get("priority_delta"), 10)


if __name__ == "__main__":
    unittest.main()
