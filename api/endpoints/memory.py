"""Phase 1 记忆与知识库 API。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/memory", tags=["memory"])


class IngestRequest(BaseModel):
    collection: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SOPRequest(BaseModel):
    category: str
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    collection: str
    query: str
    limit: int = 5


class BannedCheckRequest(BaseModel):
    text: str


class HotProductRequest(BaseModel):
    platform: str = "douyin"
    name: str
    price: float | None = None
    url: str | None = None
    sales: int | None = None
    trend_score: float | None = None


@router.get("/health")
async def memory_health():
    from memory import BannedWordsFilter, VectorStore

    vs = VectorStore()
    bw = BannedWordsFilter()
    return {
        "ok": True,
        "vector_mode": vs.mode,
        "collections": vs.collection_names(),
        "banned_words_count": len(bw.words),
    }


@router.post("/ingest")
async def ingest(req: IngestRequest):
    from memory import KnowledgeBase

    kb = KnowledgeBase()
    point_id = await kb.ingest(req.collection, req.text, req.metadata)
    return {"ok": True, "point_id": point_id}


@router.post("/search")
async def search(req: SearchRequest):
    from memory import KnowledgeBase

    kb = KnowledgeBase()
    hits = await kb.search(req.collection, req.query, limit=req.limit)
    return {"ok": True, "hits": hits}


@router.post("/sop")
async def add_sop(req: SOPRequest):
    from memory import KnowledgeBase

    kb = KnowledgeBase()
    row = await kb.add_sop(req.category, req.title, req.content, req.tags)
    return {"ok": True, "sop": row}


@router.get("/sop/search")
async def search_sop(q: str, category: str | None = None):
    from memory import KnowledgeBase

    kb = KnowledgeBase()
    hits = await kb.search_sop(q, category=category)
    return {"ok": True, "hits": hits}


@router.post("/banned/check")
async def banned_check(req: BannedCheckRequest):
    from memory import BannedWordsFilter

    f = BannedWordsFilter()
    hits = f.check(req.text)
    return {"ok": True, "hits": hits, "sanitized": f.sanitize(req.text)}


@router.post("/hot-products")
async def ingest_hot_product(req: HotProductRequest):
    from memory import KnowledgeBase

    kb = KnowledgeBase()
    row = await kb.ingest_hot_product(req.model_dump())
    return {"ok": True, "product": row}


@router.get("/context")
async def retrieve_context(q: str, platform: str = "douyin"):
    from memory import KnowledgeBase

    kb = KnowledgeBase()
    ctx = await kb.retrieve_context(query=q, platform=platform)
    return {"ok": True, "context": ctx}
