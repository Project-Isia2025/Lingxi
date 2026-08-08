"""Phase13：告警日志清理、企微响应校验、矩阵-only 工作流。"""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


class AlertLogCleanupTest(unittest.TestCase):
    def test_purge_expired_logs(self) -> None:
        from core.storage import count_alert_sent_log, init_storage, purge_expired_alert_logs, record_alert_sent

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "c.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()
                old_ts = int(time.time()) - 900000
                record_alert_sent(dedupe_key="k-old", run_id="r1", alert_type="combined_roi_low", sent_ts=old_ts)
                record_alert_sent(dedupe_key="k-new", run_id="r2", alert_type="combined_roi_high")
                self.assertEqual(count_alert_sent_log(), 2)
                out = purge_expired_alert_logs(older_than_sec=604800)
                self.assertEqual(out["deleted"], 1)
                self.assertEqual(count_alert_sent_log(), 1)


class AlertCleanupSchedulerTest(unittest.TestCase):
    def test_run_cleanup(self) -> None:
        from core.storage import init_storage, record_alert_sent
        from services.alert_cleanup_scheduler import run_alert_cleanup

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "s.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()
                record_alert_sent(
                    dedupe_key="k-stale",
                    run_id="r1",
                    alert_type="publish_failed",
                    sent_ts=int(time.time()) - 999999,
                )
                out = run_alert_cleanup(retention_sec=86400)
                self.assertTrue(out.get("ok"))
                self.assertGreaterEqual(out.get("deleted", 0), 1)


class WecomWebhookResponseTest(unittest.TestCase):
    @patch("services.roi_alert.requests.post")
    def test_wecom_errcode_zero(self, mock_post) -> None:
        from services.roi_alert import send_roi_webhook

        resp = MagicMock()
        resp.status_code = 200
        resp.text = '{"errcode":0,"errmsg":"ok"}'
        resp.json.return_value = {"errcode": 0, "errmsg": "ok"}
        mock_post.return_value = resp

        with patch.dict("os.environ", {
            "ROI_ALERT_ENABLED": "1",
            "ROI_ALERT_WEBHOOK_URL": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc",
            "ROI_ALERT_WEBHOOK_PROVIDER": "wecom",
        }):
            out = send_roi_webhook({"run_id": "r1", "event": "test", "alerts": []})
            self.assertTrue(out.get("ok"))

    @patch("services.roi_alert.requests.post")
    def test_wecom_errcode_nonzero(self, mock_post) -> None:
        from services.roi_alert import send_roi_webhook

        resp = MagicMock()
        resp.status_code = 200
        resp.text = '{"errcode":93000,"errmsg":"invalid webhook"}'
        resp.json.return_value = {"errcode": 93000, "errmsg": "invalid webhook"}
        mock_post.return_value = resp

        with patch.dict("os.environ", {
            "ROI_ALERT_ENABLED": "1",
            "ROI_ALERT_WEBHOOK_URL": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc",
            "ROI_ALERT_WEBHOOK_PROVIDER": "wecom",
        }):
            out = send_roi_webhook({"run_id": "r1", "event": "test", "alerts": []})
            self.assertFalse(out.get("ok"))


class MatrixOnlyWorkflowTest(unittest.TestCase):
    @patch("services.matrix_strategy.auto_matrix_publish")
    @patch("services.execution.run_auto_publish")
    @patch("services.execution.start_execution_job")
    @patch("services.execution.deploy_ad_plan")
    @patch("services.execution.quality_gate")
    def test_matrix_without_auto_publish(
        self,
        mock_qg,
        mock_deploy,
        mock_job,
        mock_publish,
        mock_matrix,
    ) -> None:
        mock_qg.return_value = {"passed": True, "warnings": []}
        mock_deploy.return_value = None
        mock_matrix.return_value = {"ok": True, "queued": 3, "action": "standard_matrix"}

        from orchestrator.context import WorkflowGoal
        from services.execution import build_execution

        goal = WorkflowGoal(
            keyword="护肤",
            auto_matrix_publish=True,
            auto_publish=False,
            auto_execute=False,
            video_path="D:/v.mp4",
        )
        out = build_execution(
            run_id="run-matrix-only",
            goal=goal,
            strategy={"target_platform": "douyin", "primary_keyword": "护肤", "channels": ["short_video"]},
            content={"script": "测试口播文案" * 10},
            exec_url="",
        )
        self.assertIsNotNone(out.get("matrix_publish"))
        self.assertFalse(out.get("published"))
        mock_matrix.assert_called_once()
        mock_publish.assert_not_called()
        mock_job.assert_not_called()


if __name__ == "__main__":
    unittest.main()
