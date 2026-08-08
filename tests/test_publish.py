"""自动发布单元测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()

from orchestrator.context import WorkflowContext, WorkflowGoal
from services.publish.common import build_metadata, validate_video_path


class PublishCommonTest(unittest.TestCase):
    def test_build_metadata(self) -> None:
        m = build_metadata(script="测试口播脚本内容", title="标题")
        self.assertIn("title", m)
        self.assertIn("tags", m)

    def test_validate_video_missing(self) -> None:
        ok, err = validate_video_path("/nonexistent/video.mp4")
        self.assertFalse(ok)
        self.assertIn("不存在", err)


class PublishRouterTest(unittest.TestCase):
    @patch("services.publish.router.run_publish")
    def test_dry_run(self, mock_run) -> None:
        from services.publish.router import publish_to_platform

        out = publish_to_platform("douyin", video_path="x.mp4", script="test", dry_run=True)
        self.assertTrue(out.get("dry_run"))
        mock_run.assert_not_called()

    @patch("services.publish.router.run_publish")
    @patch("services.publish.common.resolve_storage")
    @patch("services.publish.common.publish_enabled")
    @patch("services.publish.common.check_publish_quota")
    def test_publish_success(self, mock_quota, mock_enabled, mock_storage, mock_run) -> None:
        mock_quota.return_value = (True, "")
        mock_enabled.return_value = True
        mock_storage.return_value = "/fake/storage.json"
        mock_run.return_value = {"success": True, "post_url": "https://www.douyin.com/video/1", "platform": "douyin"}

        with patch("services.publish.common.validate_video_path", return_value=(True, "")):
            from services.publish.router import publish_to_platform

            out = publish_to_platform("douyin", video_path="test.mp4", script="hello")
        self.assertTrue(out.get("success"))


class ExecutionPublishTest(unittest.TestCase):
    @patch("services.execution.run_auto_publish")
    def test_auto_publish_in_execution(self, mock_pub) -> None:
        mock_pub.return_value = {"success": True, "success_count": 1, "results": []}
        from services.execution import build_execution

        goal = WorkflowGoal(keyword="护肤", auto_publish=True, video_path="demo.mp4", extra={"skip_review": True})
        script = "你是不是也在为护肤发愁？今天分享三个关键步骤，帮助改善肌肤状态。"
        out = build_execution(
            run_id="r1",
            goal=goal,
            strategy={"target_platform": "douyin", "channels": ["short_video"], "cta": "私信"},
            content={
                "script": script,
                "channel_contents": {"short_video_script": script},
                "risk_check": {"passed": True},
                "dedupe_duplicate": False,
            },
            exec_url="",
        )
        self.assertTrue(out.get("published"))
        mock_pub.assert_called_once()


if __name__ == "__main__":
    unittest.main()
