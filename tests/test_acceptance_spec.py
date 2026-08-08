"""验收规范回归测试 — 确保已实现能力不退化。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


class AcceptanceBaselineTest(unittest.TestCase):
    """已实现能力的基础验收（非全量规范）。"""

    def test_perception_golden_3s_hook(self) -> None:
        from services.perception import analyze_reference_url

        out = analyze_reference_url("https://example.com/v/x", keyword="面膜")
        segs = out.get("breakdown_segments") or []
        self.assertTrue(segs)
        hook = segs[0]
        self.assertEqual(hook.get("name"), "钩子")
        self.assertEqual(hook.get("start"), 0)
        self.assertEqual(hook.get("end"), 3)

    def test_strategy_pain_solution_angle(self) -> None:
        from services.strategy import infer_content_angle

        angle = infer_content_angle("A面膜", {"competitors": []}, {})
        self.assertIn("痛点", angle)

    def test_content_subtitles_in_mix(self) -> None:
        import inspect
        from services import video_mix

        src = inspect.getsource(video_mix._segment_clip)
        self.assertIn("drawtext", src)

    def test_asr_memory_to_kb(self) -> None:
        from services.asr_memory import ingest_asr_transcript

        self.assertTrue(callable(ingest_asr_transcript))

    def test_publish_queue_exists(self) -> None:
        from core.storage import init_storage, list_publish_queue

        init_storage()
        q = list_publish_queue(limit=1)
        self.assertIsInstance(q, list)

    def test_quality_gate_blocks_bad_content(self) -> None:
        from services.execution import quality_gate

        qg = quality_gate({"script": "短", "risk_check": {"passed": False}})
        self.assertFalse(qg.get("passed"))

    def test_replan_pre_publish_only(self) -> None:
        from orchestrator.replan import observe
        from orchestrator.context import WorkflowContext, WorkflowGoal

        ctx = WorkflowContext(goal=WorkflowGoal(keyword="test"))
        ctx.content = {"script": "x" * 50, "risk_check": {"passed": True}}
        ctx.perception = {"competitors": [{"title": "a"}], "crawl_meta": {"source": "live"}}
        ctx.execution = {"quality_gate": {"passed": True}}
        obs = observe(ctx)
        self.assertIn("needs_replan", obs)
        self.assertIsNone(obs.get("completion_rate"))

    def test_acceptance_report_runs(self) -> None:
        from scripts.acceptance_verify import run_checks

        report = run_checks()
        self.assertGreaterEqual(len(report.checks), 18)
        s = report.summary()
        self.assertGreater(s["PASS"] + s["PARTIAL"], 0)


if __name__ == "__main__":
    unittest.main()
