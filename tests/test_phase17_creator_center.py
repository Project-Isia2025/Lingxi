"""Phase17：创作者中心完播回采 + Playwright 下架。"""
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


class CreatorMetricsParseTest(unittest.TestCase):
    def test_parse_metrics_from_text(self) -> None:
        from services.creator_center import parse_metrics_from_text

        text = """
        播放量 1.2万
        点赞 860
        5s完播率 38.5%
        点击率 1.2%
        """
        out = parse_metrics_from_text(text)
        self.assertAlmostEqual(out["completion_rate"], 0.385, places=3)
        self.assertAlmostEqual(out["ctr"], 0.012, places=3)
        self.assertEqual(out["views"], 12000)

    def test_post_id_from_douyin_url(self) -> None:
        from services.creator_center import _post_id_from_url

        pid = _post_id_from_url("https://www.douyin.com/video/7123456789012345678")
        self.assertEqual(pid, "7123456789012345678")


class CreatorMetricsFetchTest(unittest.TestCase):
    def test_sample_fallback_without_storage(self) -> None:
        from services.creator_center import fetch_creator_post_metrics

        with patch("services.publish.common.resolve_storage", return_value=None):
            out = fetch_creator_post_metrics(
                platform="douyin",
                post_url="https://www.douyin.com/video/7123456789012345678",
            )
        self.assertTrue(out.get("ok"))
        self.assertIn(out.get("source"), ("sample", "sample_fallback"))
        self.assertIsNotNone(out.get("completion_rate"))

    def test_fetch_post_metrics_prefers_creator(self) -> None:
        from services.post_publish_monitor import fetch_post_metrics

        with patch("services.creator_center.fetch_creator_post_metrics") as mock_cr:
            mock_cr.return_value = {
                "ok": True,
                "source": "creator_center",
                "completion_rate": 0.55,
                "ctr": 0.02,
            }
            out = fetch_post_metrics(
                run_id="",
                platform="douyin",
                post_url="https://www.douyin.com/video/7123456789012345678",
            )
        self.assertEqual(out["source"], "creator_center")
        self.assertAlmostEqual(out["completion_rate"], 0.55)


class CreatorTakedownTest(unittest.TestCase):
    def test_dry_run_when_disabled(self) -> None:
        from services.takedown import takedown_post

        with patch.dict("os.environ", {"TAKEDOWN_ENABLED": "0"}):
            out = takedown_post(
                platform="douyin",
                post_url="https://www.douyin.com/video/7123456789012345678",
                run_id="run-td",
                reason="test",
            )
        self.assertTrue(out.get("dry_run"))

    def test_calls_creator_when_enabled(self) -> None:
        from services.takedown import takedown_post

        with patch.dict("os.environ", {"TAKEDOWN_ENABLED": "1"}), patch(
            "services.creator_center.takedown_via_creator",
            return_value={"ok": True, "dry_run": False, "message": "takedown_action_sent"},
        ) as mock_td:
            out = takedown_post(
                platform="douyin",
                post_url="https://www.douyin.com/video/7123456789012345678",
                run_id="run-td2",
                reason="low metrics",
            )
        mock_td.assert_called_once()
        self.assertFalse(out.get("dry_run"))


class PostPublishCreatorIntegrationTest(unittest.TestCase):
    def test_poll_uses_creator_metrics(self) -> None:
        from core.storage import init_storage, schedule_post_monitor
        from services.post_publish_monitor import poll_monitor

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "m.db"
            with patch("core.storage.DB_PATH", db), patch.dict(
                "os.environ",
                {"COMPLETION_RATE_MIN": "0.90", "CTR_MIN": "0.50", "TAKEDOWN_ENABLED": "0"},
            ):
                init_storage()
                mid = f"mon-{uuid.uuid4().hex[:8]}"
                schedule_post_monitor(
                    monitor_id=mid,
                    run_id="run-creator",
                    platform="douyin",
                    post_url="https://www.douyin.com/video/7123456789012345678",
                    due_ts=int(time.time()) - 10,
                )
                with patch("services.creator_center.fetch_creator_post_metrics") as mock_cr:
                    mock_cr.return_value = {
                        "ok": True,
                        "source": "creator_center",
                        "completion_rate": 0.15,
                        "ctr": 0.004,
                    }
                    result = poll_monitor(
                        {
                            "monitor_id": mid,
                            "run_id": "run-creator",
                            "platform": "douyin",
                            "post_url": "https://www.douyin.com/video/7123456789012345678",
                        }
                    )
                self.assertTrue(result.get("low_performance"))
                self.assertTrue(result.get("takedown", {}).get("dry_run"))


if __name__ == "__main__":
    unittest.main()
