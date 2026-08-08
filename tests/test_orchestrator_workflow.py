"""六 Agent 工作流单元测试（独立项目，无外网依赖）。"""
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
from orchestrator.orchestrator_agent import OrchestratorAgent, _resolve_conflict


class OrchestratorWorkflowTest(unittest.TestCase):
    def test_resolve_budget_conflict(self) -> None:
        ctx = WorkflowContext(
            goal=WorkflowGoal(keyword="测试"),
            strategy={"video_cost_plan": {"selected_provider": "volc"}},
        )
        conflict = {"type": "budget_over_limit", "selected": "template"}
        resolution = _resolve_conflict(ctx, conflict)
        self.assertEqual(resolution["action"], "downgrade_provider")
        self.assertEqual(ctx.strategy["selected_provider"], "template")

    def test_full_workflow_offline(self) -> None:
        ctx = WorkflowContext(
            goal=WorkflowGoal(
                keyword="敏感肌",
                platform="douyin",
                reference_urls=["https://example.com/v/ref"],
                auto_execute=True,
            )
        )
        with patch("services.content._llm_rewrite") as mock_llm:
            mock_llm.return_value = {
                "success": True,
                "script": "你是不是也在为敏感肌发愁？今天分享三个关键步骤。",
                "model_used": "mock",
            }
            result = OrchestratorAgent().run(ctx)
        self.assertTrue(result.ok)
        self.assertEqual(ctx.status, "completed")
        self.assertTrue(ctx.content.get("script"))
        self.assertTrue(ctx.execution.get("publish_plan"))
        self.assertTrue(ctx.execution.get("channel_execution"))

    def test_perception_competitors(self) -> None:
        from orchestrator.data_perception_agent import DataPerceptionAgent

        ctx = WorkflowContext(goal=WorkflowGoal(keyword="护肤", platform="douyin"))
        out = DataPerceptionAgent().run(ctx)
        self.assertTrue(out.ok)
        self.assertTrue(len(ctx.perception.get("competitors") or []) >= 1)

    def test_memory_kb(self) -> None:
        from orchestrator.memory_agent import MemoryAgent

        ctx = WorkflowContext(goal=WorkflowGoal(keyword="护肤", platform="douyin"))
        out = MemoryAgent().run(ctx)
        self.assertTrue(out.ok)
        self.assertIn("material_context", ctx.memory)

    def test_strategy_budget_conflict(self) -> None:
        from orchestrator.strategy_agent import StrategyAgent

        ctx = WorkflowContext(
            goal=WorkflowGoal(keyword="护肤", budget_limit=0.5, video_provider="volc"),
            perception={"competitors": [{"title": "对标", "likes": 100}], "traffic_trend": {"trend": "cold_start"}},
            memory={"geo": {}, "material_bundle": {"items": {}}},
        )
        out = StrategyAgent().run(ctx)
        self.assertTrue(out.ok)
        self.assertIn("content_angle", ctx.strategy)


if __name__ == "__main__":
    unittest.main()
