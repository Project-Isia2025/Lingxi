"""ffmpeg 混剪、投流 API、Replan 循环测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()

from orchestrator.context import WorkflowContext, WorkflowGoal
from orchestrator.replan import observe, replan, should_stop
from services.ad_optimizer import deploy_ad_plan
from services.ad_traffic.client import create_campaign
from services.video_mix import build_mix_plan


class VideoMixRenderTest(unittest.TestCase):
    @patch("services.video_mix.subprocess.run")
    @patch("services.video_mix.resolve_ffmpeg", return_value="ffmpeg")
    def test_render_mix_video(self, _ff, mock_run) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        from services.video_mix import render_mix_video

        src = ROOT / "data" / "test_src.mp4"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(b"\x00")
        plan = build_mix_plan(script="钩子。痛点。方案。证据。行动。", keyword="测试")
        with patch("services.video_mix.output_dir") as mock_out:
            out_path = ROOT / "data" / "output" / "videos"
            out_path.mkdir(parents=True, exist_ok=True)
            mock_out.return_value = out_path
            out = render_mix_video(mix_plan=plan, source_video=str(src), run_id="testrun1")
        self.assertTrue(out.get("ok"))
        self.assertTrue(out.get("output_path"))


class AdTrafficTest(unittest.TestCase):
    def test_create_campaign_dry_run(self) -> None:
        with patch("services.ad_traffic.client.ad_api_enabled", return_value=False):
            out = create_campaign(name="test", daily_budget_cny=100)
        self.assertTrue(out.get("ok"))
        self.assertTrue(out.get("dry_run"))

    def test_deploy_ad_plan_offline(self) -> None:
        plan = {"keyword": "护肤", "platform": "douyin", "daily_budget_cny": 100}
        out = deploy_ad_plan(plan, run_id="r1", sync_api=True)
        self.assertTrue(out.get("dry_run") or out.get("deployed"))
        self.assertTrue(out.get("campaign_id"))


class ReplanLoopTest(unittest.TestCase):
    def test_observe_detects_short_script(self) -> None:
        ctx = WorkflowContext(
            goal=WorkflowGoal(keyword="护肤", enable_replan=True),
            perception={"competitors": [{}], "crawl_meta": {"source": "live_crawler"}},
            content={"script": "短", "risk_check": {"passed": True}},
            execution={"quality_gate": {"passed": True}},
            strategy={"ad_plan": {}},
        )
        obs = observe(ctx)
        self.assertTrue(obs.get("needs_replan"))
        self.assertTrue(any(i["code"] == "script_too_short" for i in obs.get("issues") or []))

    def test_replan_reruns_content(self) -> None:
        ctx = WorkflowContext(goal=WorkflowGoal(keyword="护肤", enable_replan=True, max_iterations=2), plan={"iteration": 1})
        obs = {
            "needs_replan": True,
            "issues": [{"code": "content_duplicate", "severity": "medium", "message": "重复"}],
        }
        result = replan(ctx, obs)
        self.assertIn("content", result.get("rerun_agents") or [])
        self.assertTrue(result.get("should_continue"))

    def test_should_stop_when_disabled(self) -> None:
        ctx = WorkflowContext(goal=WorkflowGoal(enable_replan=False), plan={"iteration": 1})
        self.assertTrue(should_stop(ctx, {"needs_replan": True}))


class OrchestratorReplanIntegrationTest(unittest.TestCase):
    @patch("services.content._llm_rewrite")
    def test_replan_loop_runs_twice(self, mock_llm) -> None:
        mock_llm.side_effect = [
            {"success": True, "script": "短", "model_used": "mock"},
            {"success": True, "script": "你是不是也在为护肤发愁？今天分享三个关键步骤改善肌肤。", "model_used": "mock"},
        ]
        from orchestrator.orchestrator_agent import OrchestratorAgent

        ctx = WorkflowContext(
            goal=WorkflowGoal(keyword="护肤", platform="douyin", enable_replan=True, max_iterations=2, auto_execute=True),
            perception={"competitors": [{}], "crawl_meta": {"source": "curated"}},
            memory={"geo": {}, "forbidden_rows": [], "material_bundle": {"items": {}}},
        )
        # 预填 perception 让第一次 observe 触发 replan
        orch = OrchestratorAgent()
        with patch.object(orch, "_run_agents") as mock_run:
            def side_effect(c, start=0):
                if start == 0:
                    c.content = {"script": "短", "risk_check": {"passed": True}, "channel_contents": {}, "dedupe_duplicate": True, "dedupe_info": {}}
                    c.perception = {"competitors": [], "crawl_meta": {"source": "curated"}}
                    c.strategy = {"channels": ["short_video"], "ad_plan": {}, "primary_keyword": "护肤", "target_platform": "douyin"}
                    c.execution = {"quality_gate": {"passed": False}, "ready": True}
                else:
                    c.content = {
                        "script": "你是不是也在为护肤发愁？今天分享三个关键步骤改善肌肤。",
                        "risk_check": {"passed": True},
                        "channel_contents": {"short_video_script": "x" * 40},
                        "dedupe_duplicate": False,
                    }
                    c.execution = {"quality_gate": {"passed": True}, "ready": True, "auto_started": True}
                return True, []

            mock_run.side_effect = side_effect
            result = orch.run(ctx)
        self.assertTrue(result.ok)
        self.assertGreaterEqual(ctx.plan.get("iteration", 1), 2)


if __name__ == "__main__":
    unittest.main()
