"""Agent 任务路由注册表。"""
from __future__ import annotations

from typing import Any

from agents import AGENT_REGISTRY, get_agent


async def run_agent_task(agent_name: str, task: dict[str, Any]) -> dict[str, Any]:
    agent = get_agent(agent_name)
    return await agent.run(task)


def agent_capabilities() -> dict[str, list[str]]:
    return {
        "perception": ["scrape_products", "scrape_competitor", "check_traffic"],
        "strategy": ["select_product", "pricing", "bidding", "full_strategy"],
        "content": ["generate_script", "produce_video", "batch_produce"],
        "execution": ["publish", "create_ad", "optimize_ads"],
    }


def supported_platforms() -> dict[str, list[str]]:
    return {
        "perception": ["douyin", "kuaishou"],
        "execution_publish": ["douyin", "kuaishou", "weixin"],
    }
