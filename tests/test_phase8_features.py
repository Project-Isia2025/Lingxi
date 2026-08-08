"""Phase8：联合 ROI、队列优先级、Dashboard WebSocket。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


class CombinedRoiTest(unittest.TestCase):
    def test_blended_score(self) -> None:
        from services.combined_roi import compute_combined_roi

        r = compute_combined_roi(publish_roi=0.8, ad_roi=0.6)
        self.assertTrue(r.get("ok"))
        self.assertEqual(r.get("mode"), "blended")
        self.assertGreaterEqual(float(r.get("combined_roi_score") or 0), 0.65)

    def test_publish_only(self) -> None:
        from services.combined_roi import compute_combined_roi

        r = compute_combined_roi(publish_roi=0.7, ad_roi=None)
        self.assertEqual(r.get("mode"), "publish_only")
        self.assertEqual(r.get("combined_roi_score"), 0.7)

    def test_apply_for_run(self) -> None:
        from core.storage import init_storage, metrics_record
        from services.combined_roi import apply_combined_roi_for_run

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "c.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()
                metrics_record(run_id="run-x", event_type="publish_roi", value=0.75, payload={})
                metrics_record(run_id="run-x", event_type="ad_roi", value=0.55, payload={})
                out = apply_combined_roi_for_run("run-x", keyword="护肤")
                self.assertTrue(out.get("ok"))
                self.assertIn("combined_roi_score", out)


class PublishPriorityTest(unittest.TestCase):
    def test_enqueue_priority(self) -> None:
        from core.storage import enqueue_publish, init_storage, list_publish_queue

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "q.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()
                enqueue_publish(
                    job_id="low",
                    platform="douyin",
                    account_id="a",
                    video_path="v.mp4",
                    script="s",
                    priority=1,
                )
                enqueue_publish(
                    job_id="high",
                    platform="douyin",
                    account_id="a",
                    video_path="v.mp4",
                    script="s",
                    priority=10,
                )
                rows = list_publish_queue(status="queued", limit=5)
                self.assertEqual(rows[0]["job_id"], "high")


class DashboardFeedTest(unittest.TestCase):
    def test_build_feed(self) -> None:
        from services.dashboard_feed import build_perception_feed

        out = build_perception_feed(limit=5)
        self.assertTrue(out.get("ok"))
        self.assertIn("items", out)


if __name__ == "__main__":
    unittest.main()
