"""向量库封装 — Qdrant + OpenAI Embeddings。"""
from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams
except ImportError:
    QdrantClient = None  # type: ignore[misc, assignment]
    Distance = VectorParams = PointStruct = None  # type: ignore[misc, assignment]

try:
    from langchain_openai import OpenAIEmbeddings
except ImportError:
    OpenAIEmbeddings = None  # type: ignore[misc, assignment]


class _LocalEmbedder:
    """无 API Key 时的本地向量兜底（1536 维）。"""

    async def aembed_query(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        return [((h[i % len(h)] + i) % 256) / 255.0 for i in range(1536)]


class VectorStore:
    COLLECTIONS = {
        "hot_products": "历史爆款商品特征",
        "scripts": "爆款脚本模板",
        "competitors": "竞品数据",
        "sop_docs": "话术 SOP 文档",
    }

    def __init__(self) -> None:
        self._memory: dict[str, list[dict]] = {k: [] for k in self.COLLECTIONS}
        self.client = None
        self.mode = "memory"
        if QdrantClient is not None:
            host = os.environ.get("QDRANT_HOST", "localhost")
            port = int(os.environ.get("QDRANT_PORT", "6333"))
            try:
                self.client = QdrantClient(host=host, port=port, check_compatibility=False)
                self._init_collections()
                self.mode = "qdrant"
            except Exception:
                self.client = None
        if os.environ.get("OPENAI_API_KEY") and OpenAIEmbeddings is not None:
            self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        else:
            self.embeddings = _LocalEmbedder()

    def _init_collections(self) -> None:
        if self.client is None or VectorParams is None:
            return
        for name in self.COLLECTIONS:
            if not self.client.collection_exists(name):
                self.client.create_collection(
                    name,
                    vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
                )

    async def add(self, collection: str, text: str, metadata: dict) -> str:
        if collection not in self.COLLECTIONS:
            raise ValueError(f"unknown collection: {collection}")
        vector = await self.embeddings.aembed_query(text)
        point_id = metadata.get("id") or str(uuid.uuid4())
        payload = {**metadata, "text": text}
        if self.client is not None and PointStruct is not None:
            self.client.upsert(
                collection,
                points=[PointStruct(id=point_id, vector=vector, payload=payload)],
            )
        else:
            self._memory.setdefault(collection, []).append(
                {"id": point_id, "vector": vector, "payload": payload}
            )
        return str(point_id)

    async def search(
        self,
        collection: str,
        query: str,
        limit: int = 5,
        filters: dict | None = None,
    ) -> list[dict[str, Any]]:
        vector = await self.embeddings.aembed_query(query)
        if self.client is not None:
            hits = self.client.search(
                collection,
                query_vector=vector,
                limit=limit,
                query_filter=filters,
            )
            return [self._normalize_hit(h) for h in hits]
        items = self._memory.get(collection, [])
        scored = sorted(items, key=lambda x: _cosine(vector, x["vector"]), reverse=True)
        return [self._normalize_hit(x) for x in scored[:limit]]

    @staticmethod
    def _normalize_hit(hit: Any) -> dict[str, Any]:
        if isinstance(hit, dict):
            payload = hit.get("payload") or hit
            score = hit.get("score")
        else:
            payload = getattr(hit, "payload", None) or {}
            score = getattr(hit, "score", None)
        return {"score": score, **payload}

    def collection_names(self) -> list[str]:
        return list(self.COLLECTIONS.keys())


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb + 1e-9)
