"""Agent 单元测试。"""
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
async def test_perception_agent_scrape():
    from agents.perception import PerceptionAgent

    agent = PerceptionAgent()
    result = await agent.run({"type": "scrape_products", "platform": "douyin"})
    assert result["count"] >= 1
    assert "products" in result


@pytest.mark.asyncio
async def test_strategy_agent_full():
    from agents.strategy import StrategyAgent

    agent = StrategyAgent()
    result = await agent.run(
        {
            "type": "full_strategy",
            "criteria": {"keyword": "护肤", "realtime_products": [{"name": "面膜", "price": 29.9}]},
            "budget": 500,
        }
    )
    assert "product" in result or "error" in result


@pytest.mark.asyncio
async def test_content_agent_script():
    from agents.content import ContentAgent

    agent = ContentAgent()
    result = await agent.run(
        {
            "type": "generate_script",
            "product": {"name": "防晒霜", "selling_points": ["SPF50", "清爽"]},
        }
    )
    assert "script" in result
    assert result["script"]["raw_script"]


@pytest.mark.asyncio
async def test_execution_agent_publish():
    from agents.execution import ExecutionAgent

    agent = ExecutionAgent()
    result = await agent.run(
        {
            "type": "publish",
            "video_path": "data/output/videos/mock.mp4",
            "metadata": {"title": "测试", "tags": ["测试"]},
            "platforms": ["douyin"],
        }
    )
    assert "publish_result" in result
    assert result["publish_result"]["douyin"]["status"] == "success"
