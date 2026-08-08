"""四 Agent 串联 pipeline。"""
from __future__ import annotations

from typing import Any

from agents.content import ContentAgent
from agents.execution import ExecutionAgent
from agents.perception import PerceptionAgent
from agents.strategy import StrategyAgent


async def run_pipeline(body: dict[str, Any]) -> dict[str, Any]:
    """感知 -> 策略 -> 内容 -> 执行 最小链路。"""
    platform = body.get("platform", "douyin")
    keyword = body.get("keyword", "护肤")
    budget = float(body.get("budget", 500))

    perception = PerceptionAgent()
    p_out = await perception.run({"type": "scrape_products", "platform": platform, "category": keyword})

    strategy = StrategyAgent()
    s_out = await strategy.run(
        {
            "type": "full_strategy",
            "criteria": {"keyword": keyword, "realtime_products": p_out.get("products", []), "platform": platform},
            "budget": budget,
        }
    )
    if s_out.get("error"):
        return {"ok": False, "stage": "strategy", "result": s_out}

    product = s_out.get("product") or {"name": keyword}
    content = ContentAgent()
    c_out = await content.run(
        {
            "type": "produce_video",
            "product": product,
            "materials": body.get("materials", []),
            "output_path": body.get("output_path", "data/output/videos/pipeline_out.mp4"),
        }
    )

    execution = ExecutionAgent()
    e_out = await execution.run(
        {
            "type": "publish",
            "video_path": c_out.get("video_path", ""),
            "metadata": {"title": body.get("title", f"好物推荐-{keyword}"), "tags": body.get("tags", ["带货"])},
            "platforms": body.get("platforms", [platform]),
        }
    )

    return {"ok": True, "perception": p_out, "strategy": s_out, "content": c_out, "execution": e_out}
