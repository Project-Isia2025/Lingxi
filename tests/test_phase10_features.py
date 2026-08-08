"""Phase10：图表 WS、矩阵 ROI 策略、CSV 导出。"""
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


class MatrixStrategyTest(unittest.TestCase):
    @patch("services.matrix_strategy.resolve_run_roi_inputs")
    def test_full_matrix_plan(self, mock_resolve) -> None:
        mock_resolve.return_value = (0.8, 0.65)
        from services.matrix_strategy import plan_matrix_from_combined_roi

        plan = plan_matrix_from_combined_roi("run-a")
        self.assertTrue(plan.get("ok"))
        self.assertEqual(plan.get("action"), "full_matrix")
        self.assertIn("douyin", plan.get("platforms") or [])

    @patch("services.matrix_strategy.resolve_run_roi_inputs")
    def test_skip_low_roi(self, mock_resolve) -> None:
        mock_resolve.return_value = (0.2, 0.1)
        from services.matrix_strategy import plan_matrix_from_combined_roi

        plan = plan_matrix_from_combined_roi("run-b")
        self.assertEqual(plan.get("action"), "skip")


class RoiExportTest(unittest.TestCase):
    def test_export_csv(self) -> None:
        from core.storage import init_storage, metrics_record
        from services.roi_export import export_roi_csv

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "e.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()
                metrics_record(run_id="r1", event_type="combined_roi", value=0.66, payload={"platform": "douyin"})
                csv_text = export_roi_csv(days=14)
                self.assertIn("combined_roi", csv_text)
                self.assertIn("r1", csv_text)


class DashboardHubTest(unittest.TestCase):
    def test_analytics_connection_count(self) -> None:
        from services.dashboard_hub import analytics_connection_count, connection_count

        self.assertEqual(connection_count(), 0)
        self.assertEqual(analytics_connection_count(), 0)


if __name__ == "__main__":
    unittest.main()
