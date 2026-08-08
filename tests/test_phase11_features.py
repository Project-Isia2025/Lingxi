"""Phase11：工作流矩阵发布、ROI 邮件、Webhook 告警。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


class RoiAlertTest(unittest.TestCase):
    def test_evaluate_high_alert(self) -> None:
        from services.roi_alert import evaluate_roi_alerts

        alerts = evaluate_roi_alerts(run_id="r1", combined_roi=0.85)
        self.assertTrue(any(a["type"] == "combined_roi_high" for a in alerts))

    @patch("services.roi_alert.send_roi_webhook")
    def test_dispatch(self, mock_send) -> None:
        mock_send.return_value = {"ok": True}
        from services.roi_alert import dispatch_roi_alerts

        out = dispatch_roi_alerts(run_id="r1-dispatch-test", combined_roi=0.2, force=True)
        self.assertTrue(out.get("alerts"))
        mock_send.assert_called_once()


class RoiEmailTest(unittest.TestCase):
    def test_save_report_file_only(self) -> None:
        from core.storage import init_storage
        from services.roi_email import send_roi_report_email

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "r.db"
            reports = Path(td) / "reports"
            with patch("core.storage.DB_PATH", db), patch("services.roi_email.bootstrap.project_root", return_value=Path(td)):
                init_storage()
                out = send_roi_report_email(days=7)
                self.assertTrue(out.get("ok"))
                self.assertFalse(out.get("emailed"))


class WorkflowMatrixTest(unittest.TestCase):
    @patch("services.matrix_strategy.auto_matrix_publish")
    @patch("services.execution.deploy_ad_plan")
    @patch("services.execution.quality_gate")
    def test_build_execution_matrix(self, mock_qg, mock_deploy, mock_matrix) -> None:
        mock_qg.return_value = {"passed": True, "warnings": []}
        mock_deploy.return_value = None
        mock_matrix.return_value = {"ok": True, "queued": 2, "action": "standard_matrix"}

        from orchestrator.context import WorkflowGoal
        from services.execution import build_execution

        goal = WorkflowGoal(
            keyword="护肤",
            auto_matrix_publish=True,
            video_path="D:/v.mp4",
        )
        out = build_execution(
            run_id="run-m1",
            goal=goal,
            strategy={"target_platform": "douyin", "primary_keyword": "护肤", "channels": ["short_video"]},
            content={"script": "测试口播文案" * 10},
            exec_url="",
        )
        self.assertIsNotNone(out.get("matrix_publish"))
        mock_matrix.assert_called_once()


class ReportSchedulerTest(unittest.TestCase):
    def test_status(self) -> None:
        from services.report_scheduler import get_report_scheduler_status

        st = get_report_scheduler_status()
        self.assertTrue(st.get("ok"))


if __name__ == "__main__":
    unittest.main()
