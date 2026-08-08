"""Phase12：Webhook 格式、告警去重、CLI 矩阵参数。"""
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


class AlertFormatTest(unittest.TestCase):
    def test_feishu_format(self) -> None:
        from services.roi_alert_format import format_feishu_payload

        body = format_feishu_payload({
            "run_id": "r1",
            "event": "test",
            "alerts": [{"level": "info", "message": "联合 ROI 优秀"}],
        })
        self.assertEqual(body["msg_type"], "text")
        self.assertIn("ROI", body["content"]["text"])

    def test_wecom_format(self) -> None:
        from services.roi_alert_format import format_wecom_payload

        body = format_wecom_payload({"run_id": "r1", "event": "test", "alerts": []})
        self.assertEqual(body["msgtype"], "text")

    def test_detect_feishu(self) -> None:
        from services.roi_alert_format import detect_provider

        self.assertEqual(detect_provider("https://open.feishu.cn/open-apis/bot/v2/hook/xxx"), "feishu")


class AlertDedupTest(unittest.TestCase):
    def test_dedup_blocks_repeat(self) -> None:
        from core.storage import init_storage, record_alert_sent
        from services.roi_alert_dedup import build_dedupe_key, filter_deduped_alerts

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "a.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()
                alert = {"type": "combined_roi_high", "value": 0.8, "message": "high"}
                key = build_dedupe_key(run_id="r1", alert=alert, event="combined_roi")
                record_alert_sent(dedupe_key=key, run_id="r1", alert_type="combined_roi_high")
                passed, skipped = filter_deduped_alerts(
                    run_id="r1",
                    alerts=[alert],
                    event="combined_roi",
                )
                self.assertEqual(len(passed), 0)
                self.assertEqual(len(skipped), 1)


class AlertDispatchDedupTest(unittest.TestCase):
    @patch("services.roi_alert.send_roi_webhook")
    def test_dispatch_skips_deduped(self, mock_send) -> None:
        from core.storage import init_storage, record_alert_sent
        from services.roi_alert import dispatch_roi_alerts
        from services.roi_alert_dedup import build_dedupe_key

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "d.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()
                alert = {"type": "combined_roi_low", "value": 0.2, "level": "warning", "message": "low"}
                key = build_dedupe_key(run_id="r2", alert=alert, event="combined_roi")
                record_alert_sent(dedupe_key=key, run_id="r2", alert_type="combined_roi_low")
                out = dispatch_roi_alerts(run_id="r2", combined_roi=0.2, event="combined_roi")
                self.assertFalse(out.get("sent"))
                mock_send.assert_not_called()


class CliArgsTest(unittest.TestCase):
    def test_parse_platforms_helper(self) -> None:
        import cli

        self.assertEqual(cli._parse_platforms("douyin, xiaohongshu"), ["douyin", "xiaohongshu"])


if __name__ == "__main__":
    unittest.main()
