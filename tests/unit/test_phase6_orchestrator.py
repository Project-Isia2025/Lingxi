"""Phase 6 LangGraph 总控大脑单元测试。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


def test_legacy_orchestrator_still_importable():
    from orchestrator import OrchestratorAgent, run_workflow
    from orchestrator.context import WorkflowGoal

    assert OrchestratorAgent
    assert callable(run_workflow)
    assert WorkflowGoal


def test_langgraph_coexists_with_legacy():
    from orchestrator import Orchestrator, OrchestratorAgent, build_initial_state

    assert Orchestrator.__name__ == "Orchestrator"
    assert OrchestratorAgent.__name__ == "OrchestratorAgent"
    state = build_initial_state(goal="test")
    assert state["goal"] == "test"


def test_orchestrator_nodes_routing():
    from orchestrator.nodes import OrchestratorNodes
    from orchestrator.state import build_initial_state

    nodes = OrchestratorNodes()
    state = build_initial_state(goal="x", total_budget=1000)
    state["strategy_data"] = {"bidding": {"bid_cpc": 3.0}}
    assert nodes.needs_approval(state) is True
    state["strategy_data"] = {"bidding": {"bid_cpc": 0.5}}
    assert nodes.needs_approval(state) is False


def test_roi_monitor():
    from orchestrator.roi_monitor import ROIMonitor

    m = ROIMonitor()
    assert m._grade(2.5) == "A"
    stop, reason = m.should_stop({"iteration": 11, "max_iterations": 10, "current_roi": 2.0, "total_budget": 100, "total_spend": 50})
    assert stop and reason == "max_iterations"


@pytest.mark.asyncio
async def test_langgraph_full_pipeline():
    from orchestrator.graph import Orchestrator
    from orchestrator.state import build_initial_state

    orch = Orchestrator()
    state = build_initial_state(goal="测试带货", platform="douyin", total_budget=100, max_iterations=1)
    result = await orch.graph.ainvoke(state)
    assert result["iteration"] > 0
    assert "perception_data" in result
    assert "execution_data" in result
