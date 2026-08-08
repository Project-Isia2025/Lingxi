"""记忆库 PostgreSQL 仓储 — 结构化数据读写。"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from memory.models import AdCampaign, AgentDecision, HotProduct, SOPDocumentModel


class MemoryRepository:
    """hot_products / ad_campaigns / agent_decisions / sop_documents 持久化。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_hot_product(self, data: dict[str, Any]) -> HotProduct:
        platform = str(data.get("platform") or "douyin")
        name = str(data.get("product_name") or data.get("name") or "").strip()
        stmt = select(HotProduct).where(
            HotProduct.platform == platform,
            HotProduct.product_name == name,
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = HotProduct(
                platform=platform,
                product_name=name,
                product_url=data.get("product_url") or data.get("url"),
                price=data.get("price"),
                sales_count=_to_int(data.get("sales_count") or data.get("sales")),
                trend_score=data.get("trend_score"),
                metadata_json=data.get("metadata") or {},
            )
            self.session.add(row)
        else:
            row.product_url = data.get("product_url") or data.get("url") or row.product_url
            row.price = data.get("price") if data.get("price") is not None else row.price
            row.sales_count = _to_int(data.get("sales_count") or data.get("sales")) or row.sales_count
            row.trend_score = data.get("trend_score") if data.get("trend_score") is not None else row.trend_score
            row.metadata_json = {**(row.metadata_json or {}), **(data.get("metadata") or {})}
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_hot_products(self, platform: str | None = None, limit: int = 20) -> list[dict]:
        stmt = select(HotProduct).order_by(HotProduct.trend_score.desc().nullslast()).limit(limit)
        if platform:
            stmt = stmt.where(HotProduct.platform == platform)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_hot_product_to_dict(r) for r in rows]

    async def create_ad_campaign(self, data: dict[str, Any]) -> AdCampaign:
        row = AdCampaign(
            platform=str(data.get("platform") or "douyin"),
            product_id=data.get("product_id"),
            video_url=data.get("video_url"),
            daily_budget=data.get("daily_budget"),
            bid_cpc=data.get("bid_cpc"),
            impressions=int(data.get("impressions") or 0),
            clicks=int(data.get("clicks") or 0),
            conversions=int(data.get("conversions") or 0),
            spend=float(data.get("spend") or 0),
            revenue=float(data.get("revenue") or 0),
            status=str(data.get("status") or "active"),
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def log_agent_decision(
        self,
        *,
        agent_name: str,
        decision_type: str,
        input_data: dict | None = None,
        output_data: dict | None = None,
        confidence: float | None = None,
    ) -> AgentDecision:
        row = AgentDecision(
            agent_name=agent_name,
            decision_type=decision_type,
            input_data=input_data,
            output_data=output_data,
            confidence=confidence,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def add_sop_row(self, category: str, title: str, content: str, tags: list[str]) -> SOPDocumentModel:
        row = SOPDocumentModel(category=category, title=title, content=content, tags=tags)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_sop(self, category: str | None = None, limit: int = 20) -> list[dict]:
        stmt = select(SOPDocumentModel).order_by(SOPDocumentModel.updated_at.desc()).limit(limit)
        if category:
            stmt = stmt.where(SOPDocumentModel.category == category)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            {
                "id": r.id,
                "category": r.category,
                "title": r.title,
                "content": r.content,
                "tags": r.tags or [],
            }
            for r in rows
        ]


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).replace(",", "").replace("+", ""))
    except (ValueError, TypeError):
        return None


def _hot_product_to_dict(row: HotProduct) -> dict:
    return {
        "id": row.id,
        "platform": row.platform,
        "product_name": row.product_name,
        "product_url": row.product_url,
        "price": float(row.price) if row.price is not None else None,
        "sales_count": row.sales_count,
        "trend_score": row.trend_score,
        "metadata": row.metadata_json or {},
    }


class LocalMemoryStore:
    """无 PostgreSQL 时的进程内兜底。"""

    def __init__(self) -> None:
        self.hot_products: list[dict] = []
        self.ad_campaigns: list[dict] = []
        self.agent_decisions: list[dict] = []
        self.sop_documents: list[dict] = []

    async def upsert_hot_product(self, data: dict[str, Any]) -> dict:
        platform = str(data.get("platform") or "douyin")
        name = str(data.get("product_name") or data.get("name") or "")
        for item in self.hot_products:
            if item["platform"] == platform and item["product_name"] == name:
                item.update(data)
                return item
        row = {"id": len(self.hot_products) + 1, **data, "platform": platform, "product_name": name}
        self.hot_products.append(row)
        return row

    async def list_hot_products(self, platform: str | None = None, limit: int = 20) -> list[dict]:
        rows = self.hot_products
        if platform:
            rows = [r for r in rows if r.get("platform") == platform]
        return rows[:limit]

    async def create_ad_campaign(self, data: dict[str, Any]) -> dict:
        row = {"id": len(self.ad_campaigns) + 1, **data}
        self.ad_campaigns.append(row)
        return row

    async def log_agent_decision(self, **kwargs) -> dict:
        row = {"id": len(self.agent_decisions) + 1, **kwargs}
        self.agent_decisions.append(row)
        return row

    async def add_sop_row(self, category: str, title: str, content: str, tags: list[str]) -> dict:
        row = {"id": len(self.sop_documents) + 1, "category": category, "title": title, "content": content, "tags": tags}
        self.sop_documents.append(row)
        return row

    async def list_sop(self, category: str | None = None, limit: int = 20) -> list[dict]:
        rows = self.sop_documents
        if category:
            rows = [r for r in rows if r.get("category") == category]
        return rows[:limit]


async def get_memory_store(session: AsyncSession | None = None):
    if session is not None:
        return MemoryRepository(session)
    return LocalMemoryStore()
