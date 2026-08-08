"""知识库管理 — 所有 Agent 的长期记忆入口。"""
from __future__ import annotations

from typing import Any

from infra.database import SessionLocal
from memory.banned_words import BannedWordsFilter
from memory.repository import LocalMemoryStore, MemoryRepository, get_memory_store
from memory.sop_store import SOPDocument
from memory.vector_store import VectorStore


class KnowledgeBase:
    """统一知识库：向量检索 + 结构化存储 + 违禁词 + SOP。"""

    COLLECTIONS = VectorStore.COLLECTIONS

    def __init__(self, session=None) -> None:
        self.session = session
        self.vector_store = VectorStore()
        self.sop = SOPDocument(session=session)
        self.banned_words = BannedWordsFilter()
        self._store = None

    async def _repo(self):
        if self._store is None:
            self._store = await get_memory_store(self.session)
        return self._store

    async def ingest(self, collection: str, text: str, metadata: dict) -> str:
        """写入向量库，并同步到 SQLite KB（若可用）。"""
        point_id = await self.vector_store.add(collection, text, metadata)
        try:
            from services.knowledge import kb_upsert

            tags = metadata.get("tags") or []
            kb_upsert(
                library=collection,
                title=str(metadata.get("title") or metadata.get("product_name") or ""),
                body=text,
                tags=",".join(tags) if isinstance(tags, list) else str(tags),
                platform=str(metadata.get("platform") or "douyin"),
            )
        except Exception:
            pass
        return point_id

    async def search(self, collection: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        results = await self.vector_store.search(collection, query, limit=limit)
        if results:
            return results
        try:
            from services.knowledge import kb_search

            return list(kb_search(query=query, library=collection, limit=limit))
        except Exception:
            return []

    async def ingest_hot_product(self, product: dict[str, Any]) -> dict[str, Any]:
        """爆款商品：PostgreSQL + 向量库双写。"""
        text = f"{product.get('name') or product.get('product_name')} {product.get('price')} {product.get('platform')}"
        meta = {
            "title": product.get("name") or product.get("product_name"),
            "platform": product.get("platform"),
            **product,
        }
        await self.ingest("hot_products", text, meta)
        repo = await self._repo()
        row = await repo.upsert_hot_product(
            {
                "platform": product.get("platform"),
                "product_name": product.get("name") or product.get("product_name"),
                "product_url": product.get("url") or product.get("product_url"),
                "price": product.get("price"),
                "sales_count": product.get("sales") or product.get("sales_count"),
                "trend_score": product.get("trend_score") or product.get("score"),
                "metadata": product,
            }
        )
        if isinstance(row, dict):
            return row
        return {
            "id": row.id,
            "platform": row.platform,
            "product_name": row.product_name,
            "price": float(row.price) if row.price is not None else None,
        }

    async def log_decision(
        self,
        *,
        agent_name: str,
        decision_type: str,
        input_data: dict | None = None,
        output_data: dict | None = None,
        confidence: float | None = None,
    ) -> dict:
        repo = await self._repo()
        row = await repo.log_agent_decision(
            agent_name=agent_name,
            decision_type=decision_type,
            input_data=input_data,
            output_data=output_data,
            confidence=confidence,
        )
        return row if isinstance(row, dict) else {"id": row.id, "agent_name": row.agent_name}

    async def search_sop(self, query: str, category: str | None = None) -> list[dict]:
        return await self.sop.search_sop(query, category=category)

    async def add_sop(self, category: str, title: str, content: str, tags: list[str] | None = None) -> dict:
        return await self.sop.add_sop(category, title, content, tags or [])

    def check_banned_words(self, text: str) -> list[str]:
        return self.banned_words.check(text)

    def sanitize_text(self, text: str) -> str:
        return self.banned_words.sanitize(text)

    async def retrieve_context(
        self,
        *,
        query: str,
        platform: str = "douyin",
        include_sop: bool = True,
    ) -> dict[str, Any]:
        """Agent 召回统一上下文 — 对标 services.knowledge.retrieve_memory。"""
        scripts = await self.search("scripts", query, limit=3)
        hot = await self.search("hot_products", query, limit=3)
        competitors = await self.search("competitors", query, limit=3)
        sop_entries = await self.search_sop(query) if include_sop else []
        forbidden = self.banned_words.check(query)
        return {
            "query": query,
            "platform": platform,
            "scripts": scripts,
            "hot_products": hot,
            "competitors": competitors,
            "sop_entries": sop_entries,
            "forbidden_hits_in_query": forbidden,
            "vector_mode": self.vector_store.mode,
        }


async def with_pg_session():
    """获取 PostgreSQL 异步会话（供 API / 脚本使用）。"""
    async with SessionLocal() as session:
        yield session
