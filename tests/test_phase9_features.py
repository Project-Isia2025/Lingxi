"""Phase9：联合 ROI 调价、动态优先级、ROI 图表。"""
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


class CombinedRoiBidTest(unittest.TestCase):
    def test_evaluate_increase(self) -> None:
        from services.combined_roi_bid import evaluate_combined_roi_bid

        d = evaluate_combined_roi_bid(combined_roi_score=0.8, daily_budget_cny=100, publish_roi=0.75, ad_roi=0.6)
        self.assertEqual(d["action"], "increase_budget")

    def test_evaluate_decrease(self) -> None:
        from services.combined_roi_bid import evaluate_combined_roi_bid

        d = evaluate_combined_roi_bid(combined_roi_score=0.3, daily_budget_cny=100)
        self.assertEqual(d["action"], "decrease_budget")

    @patch("services.combined_roi_bid.apply_bid_decision")
    @patch("services.combined_roi_bid.get_ad_campaign_by_run")
    @patch("services.combined_roi_bid.resolve_run_roi_inputs")
    def test_run_for_run(self, mock_resolve, mock_campaign, mock_apply) -> None:
        mock_resolve.return_value = (0.8, 0.6)
        mock_campaign.return_value = {"daily_budget": 100, "dry_run": True, "campaign_id": "dry_1"}
        mock_apply.return_value = {"ok": True, "applied": True}
        from services.combined_roi_bid import run_combined_roi_bid_for_run

        out = run_combined_roi_bid_for_run("run-1", apply=True)
        self.assertTrue(out.get("ok"))


class PublishPriorityTest(unittest.TestCase):
    def test_priority_from_score(self) -> None:
        from services.publish_priority import priority_from_combined_score

        self.assertEqual(priority_from_combined_score(0.8), 15)
        self.assertEqual(priority_from_combined_score(0.5), 5)

    def test_refresh_queue(self) -> None:
        from core.storage import enqueue_publish, init_storage, list_publish_queue
        from services.publish_priority import refresh_queue_priorities

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "p.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()
                enqueue_publish(
                    job_id="j1",
                    platform="douyin",
                    account_id="a",
                    video_path="v.mp4",
                    script="s",
                    run_id="run-high",
                    priority=1,
                )
                with patch("services.publish_priority.resolve_publish_priority", return_value=12):
                    out = refresh_queue_priorities()
                self.assertTrue(out.get("ok"))
                rows = list_publish_queue(status="queued", limit=5)
                self.assertEqual(int(rows[0].get("priority") or 0), 12)


class DashboardMetricsTest(unittest.TestCase):
    def test_build_chart(self) -> None:
        from core.storage import init_storage, metrics_record
        from services.dashboard_metrics import build_metrics_chart

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "m.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()
                metrics_record(run_id="r1", event_type="combined_roi", value=0.7, payload={})
                chart = build_metrics_chart(days=14)
                self.assertTrue(chart.get("ok"))
                self.assertIn("series", chart)


if __name__ == "__main__":
    unittest.main()
