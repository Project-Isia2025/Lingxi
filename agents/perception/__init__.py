"""数据感知 Agent — 爬虫 / 流量监控 / 数据清洗。"""
from __future__ import annotations

from agents.base import BaseAgent
from agents.perception.cleaners import clean_products
from agents.perception.monitor import TrafficMonitor
from agents.perception.scraper import CompetitorScraper
from memory.knowledge_base import KnowledgeBase


class PerceptionAgent(BaseAgent):
    """数据感知 Agent - 负责采集和清洗外部数据。"""

    def __init__(self) -> None:
        super().__init__("perception")
        self.scraper = CompetitorScraper()
        self.monitor = TrafficMonitor()
        self.kb = KnowledgeBase()

    async def execute(self, task: dict) -> dict:
        task_type = task.get("type")

        if task_type == "scrape_products":
            platform = task["platform"]
            products = await self.scraper.scrape_hot_products(platform, task.get("category"))
            cleaned = await self._clean_and_store(products, platform)
            await self.kb.log_decision(
                agent_name=self.name,
                decision_type="scrape_products",
                input_data={"platform": platform, "category": task.get("category")},
                output_data={"count": len(cleaned)},
                confidence=0.9 if cleaned else 0.3,
            )
            return {"products": cleaned, "count": len(cleaned)}

        if task_type == "scrape_competitor":
            data = await self.scraper.scrape_competitor_videos(task["competitor_id"])
            if data.get("videos"):
                for v in data["videos"][:5]:
                    await self.kb.ingest(
                        "competitors",
                        f"{v.get('title','')} {v.get('likes',0)}",
                        {"title": v.get("title"), "platform": task.get("platform", "douyin"), **v},
                    )
            return {"competitor_data": data}

        if task_type == "check_traffic":
            report = await self.monitor.check_all()
            return {"traffic_report": report}

        if task_type == "perceive_market":
            return await self._perceive_market(task)

        raise ValueError(f"Unknown task type: {task_type}")

    async def _perceive_market(self, task: dict) -> dict:
        """桥接现有 services.perception 能力。"""
        try:
            from services.perception import perceive_market

            out = perceive_market(
                keyword=task.get("keyword", ""),
                platform=task.get("platform", "douyin"),
                reference_urls=task.get("reference_urls") or [],
                include_hotlist=task.get("include_hotlist", True),
            )
            for c in out.get("competitors") or []:
                if isinstance(c, dict) and c.get("title"):
                    await self.kb.ingest(
                        "competitors",
                        f"{c.get('title')} {c.get('body','')[:200]}",
                        {"title": c.get("title"), "platform": task.get("platform", "douyin"), **c},
                    )
            return {"perception": out}
        except Exception as exc:
            return {"perception": {}, "error": str(exc)}

    async def _clean_and_store(self, products: list, platform: str) -> list:
        cleaned = clean_products(products, platform)
        stored = []
        for p in cleaned:
            row = await self.kb.ingest_hot_product(
                {
                    "platform": platform,
                    "name": p["name"],
                    "price": p.get("price"),
                    "url": p.get("url"),
                    "sales": p.get("sales"),
                }
            )
            stored.append({**p, "stored_id": row.get("id")})
        return stored


__all__ = ["PerceptionAgent", "CompetitorScraper", "TrafficMonitor", "clean_products"]
