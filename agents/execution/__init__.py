"""执行 Agent — 多平台发布 / 投流调优。"""
from __future__ import annotations

from agents.base import BaseAgent
from agents.execution.ad_optimizer import AdOptimizer
from agents.execution.publisher import Publisher
from memory.knowledge_base import KnowledgeBase


class ExecutionAgent(BaseAgent):
    SUPPORTED_PLATFORMS = ("douyin", "kuaishou", "weixin")

    def __init__(self) -> None:
        super().__init__("execution")
        self.publisher = Publisher()
        self.optimizer = AdOptimizer()
        self.kb = KnowledgeBase()

    async def execute(self, task: dict) -> dict:
        task_type = task.get("type")

        if task_type == "publish":
            platforms = task.get("platforms", ["douyin"])
            result = await self.publisher.publish(
                video_path=task["video_path"],
                metadata=task["metadata"],
                platforms=platforms,
            )
            await self.kb.log_decision(
                agent_name=self.name,
                decision_type="publish",
                input_data={"platforms": platforms, "title": task["metadata"].get("title")},
                output_data=result,
                confidence=sum(1 for v in result.values() if v.get("status") == "success") / max(len(platforms), 1),
            )
            return {"publish_result": result}

        if task_type == "create_ad":
            result = await self.publisher.create_ad(
                video_id=task["video_id"],
                budget=task["budget"],
                bid=task["bid"],
                targeting=task.get("targeting", {}),
                platform=task.get("platform", "douyin"),
            )
            return {"ad_campaign": result}

        if task_type == "optimize_ads":
            report = await self.optimizer.run_once()
            return {"optimization_report": report}

        if task_type == "full_execution":
            pub = await self.execute(
                {
                    "type": "publish",
                    "video_path": task["video_path"],
                    "metadata": task["metadata"],
                    "platforms": task.get("platforms", ["douyin", "kuaishou", "weixin"]),
                }
            )
            ad = None
            if task.get("create_ad") and task.get("video_id"):
                ad = await self.execute(
                    {
                        "type": "create_ad",
                        "video_id": task["video_id"],
                        "budget": task.get("budget", 100),
                        "bid": task.get("bid", 0.5),
                        "targeting": task.get("targeting", {}),
                        "platform": task.get("platform", "douyin"),
                    }
                )
            opt = await self.execute({"type": "optimize_ads"})
            return {"publish": pub, "ad": ad, "optimization": opt}

        raise ValueError(f"Unknown task type: {task_type}")


__all__ = ["ExecutionAgent", "Publisher", "AdOptimizer"]
