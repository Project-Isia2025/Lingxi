"""集成测试 — LangGraph 全链路。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


@pytest.mark.asyncio
async def test_full_pipeline():
    """端到端：感知 -> 策略 -> 内容 -> 执行 -> ROI。"""
    from orchestrator.graph import Orchestrator
    from orchestrator.state import build_initial_state

    orchestrator = Orchestrator()
    state = build_initial_state(goal="测试带货", platform="douyin", total_budget=100, max_iterations=1)

    result = await orchestrator.graph.ainvoke(state)

    assert result["iteration"] > 0
    assert "perception_data" in result
    assert "strategy_data" in result
    assert "content_data" in result
    assert "execution_data" in result
    assert "current_roi" in result
