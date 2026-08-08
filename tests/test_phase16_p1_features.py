"""Phase16 P1：BGM/视觉去重/AI成片/发布后监控。"""
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


class BgmMixTest(unittest.TestCase):
    def test_pick_bgm_path(self) -> None:
        from services.bgm import pick_bgm_for_mix

        bgm = pick_bgm_for_mix(keyword="护肤")
        self.assertTrue(bgm.get("name"))


class VisualDedupTest(unittest.TestCase):
    def test_visual_filters_deterministic(self) -> None:
        from services.video_mix import _visual_filters

        a = _visual_filters(run_id="r1", segment_idx=0, variant="A")
        b = _visual_filters(run_id="r1", segment_idx=0, variant="A")
        self.assertEqual(a, b)
        self.assertIn("setpts", a)


class VideoProviderTest(unittest.TestCase):
    def test_mock_produce_with_source(self) -> None:
        from services.video_providers.router import produce_video

        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src.mp4"
            src.write_bytes(b"fake")
            out = produce_video(
                provider="volc",
                script="测试",
                run_id="run-v1",
                source_video=str(src),
            )
            self.assertTrue(out.get("ok"))
            self.assertEqual(out.get("mode"), "mock")
            self.assertTrue(Path(out["output_path"]).is_file())


class PostPublishMonitorTest(unittest.TestCase):
    def test_low_performance_triggers_takedown(self) -> None:
        from core.storage import init_storage, schedule_post_monitor
        from services.post_publish_monitor import poll_monitor

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "m.db"
            with patch("core.storage.DB_PATH", db), patch.dict(
                "os.environ",
                {"COMPLETION_RATE_MIN": "0.90", "CTR_MIN": "0.50"},
            ):
                init_storage()
                mid = f"mon-{uuid.uuid4().hex[:8]}"
                schedule_post_monitor(
                    monitor_id=mid,
                    run_id="run-low",
                    platform="douyin",
                    post_url="https://example.com/post/1",
                    due_ts=int(time.time()) - 10,
                )
                with patch("services.post_publish_monitor.fetch_post_metrics") as mock_metrics:
                    mock_metrics.return_value = {
                        "ok": True,
                        "completion_rate": 0.12,
                        "ctr": 0.002,
                        "source": "test",
                    }
                    out = poll_monitor({
                        "monitor_id": mid,
                        "run_id": "run-low",
                        "platform": "douyin",
                        "post_url": "https://x",
                    })
                self.assertTrue(out.get("low_performance"))
                self.assertIn("takedown", out)


class ReplanPostPublishTest(unittest.TestCase):
    def test_observe_low_completion(self) -> None:
        from orchestrator.context import WorkflowContext, WorkflowGoal
        from orchestrator.replan import observe, replan

        ctx = WorkflowContext(goal=WorkflowGoal(keyword="test", enable_replan=True))
        ctx.execution = {"post_publish_metrics": {"completion_rate": 0.15, "ctr": 0.003}}
        ctx.content = {"script": "x" * 50, "risk_check": {"passed": True}}
        ctx.perception = {"competitors": [{"title": "a"}], "crawl_meta": {"source": "live"}}
        obs = observe(ctx)
        self.assertTrue(any(i["code"] == "low_completion_rate" for i in obs.get("issues") or []))
        plan = replan(ctx, obs)
        self.assertIn("content", plan.get("rerun_agents") or [])


class ContentBgmPlanTest(unittest.TestCase):
    def test_mix_plan_has_bgm(self) -> None:
        from services.content import generate_content

        out = generate_content(
            source="测试源文案",
            keyword="护肤",
            angle="痛点+解决方案",
            memory={"forbidden_rows": [], "geo": {}},
            strategy={"variants": []},
        )
        self.assertIn("bgm", out.get("mix_plan") or {})


if __name__ == "__main__":
    unittest.main()
