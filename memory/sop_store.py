"""话术 SOP 存储 — PostgreSQL + Qdrant 双写。"""
from __future__ import annotations

from typing import Any

from memory.repository import LocalMemoryStore, MemoryRepository, get_memory_store
from memory.vector_store import VectorStore


class SOPDocument:
    """话术 SOP 文档模型。"""

    def __init__(self, session=None) -> None:
        self.session = session
        self.vector_store = VectorStore()
        self._store = None

    async def _repo(self):
        if self._store is None:
            self._store = await get_memory_store(self.session)
        return self._store

    async def add_sop(self, category: str, title: str, content: str, tags: list[str]) -> dict[str, Any]:
        """添加话术 SOP — 同时写入 PostgreSQL（结构化）和 Qdrant（向量检索）。"""
        meta = {
            "category": category,
            "title": title,
            "tags": tags,
        }
        point_id = await self.vector_store.add("sop_docs", f"{title}\n{content}", meta)
        repo = await self._repo()
        if isinstance(repo, MemoryRepository):
            row = await repo.add_sop_row(category, title, content, tags)
            return {
                "id": row.id,
                "category": category,
                "title": title,
                "tags": tags,
                "vector_id": point_id,
            }
        row = await repo.add_sop_row(category, title, content, tags)
        return {**row, "vector_id": point_id}

    async def search_sop(self, query: str, category: str | None = None) -> list[dict]:
        """语义检索 SOP — 向量检索 + 返回完整内容。"""
        hits = await self.vector_store.search("sop_docs", query, limit=10)
        out: list[dict] = []
        seen: set[str] = set()
        for payload in hits:
            if category and payload.get("category") != category:
                continue
            title = str(payload.get("title") or "")
            key = f"{category}:{title}"
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "title": title,
                    "content": payload.get("text") or payload.get("content"),
                    "category": payload.get("category"),
                    "tags": payload.get("tags") or [],
                    "score": payload.get("score"),
                }
            )
        if not out:
            repo = await self._repo()
            rows = await repo.list_sop(category=category, limit=10)
            for row in rows:
                if query.lower() in f"{row.get('title','')} {row.get('content','')}".lower():
                    out.append(row)
        return out

    async def list_categories(self) -> list[str]:
        repo = await self._repo()
        rows = await repo.list_sop(limit=100)
        return sorted({str(r.get("category") or "") for r in rows if r.get("category")})
