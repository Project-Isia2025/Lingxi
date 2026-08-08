"""Phase 1 记忆与知识库单元测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


def test_banned_words_json_exists():
    path = ROOT / "memory" / "data" / "banned_words.json"
    assert path.is_file()
    words = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(words, list)
    assert len(words) >= 10
    assert "最好" in words
    assert "国家级" in words


@pytest.mark.asyncio
async def test_vector_store_crud():
    from memory.vector_store import VectorStore

    vs = VectorStore()
    pid = await vs.add("competitors", "竞品A 播放量100万", {"title": "竞品A", "platform": "douyin"})
    hits = await vs.search("competitors", "竞品", limit=5)
    assert pid
    assert hits
    assert hits[0].get("title") == "竞品A"


def test_banned_words_filter():
    from memory.banned_words import BannedWordsFilter

    f = BannedWordsFilter()
    assert f.filter_metadata()["count"] >= 10
    hits = f.check("国家级最好，100%有效，立即见效")
    assert "最好" in hits
    assert "100%" in hits
    assert "****" in f.sanitize("最好的")


@pytest.mark.asyncio
async def test_sop_store():
    from memory.sop_store import SOPDocument

    sop = SOPDocument()
    row = await sop.add_sop("开场", "痛点钩子", "你是不是也有XXX困扰？", ["hook"])
    hits = await sop.search_sop("痛点", category="开场")
    assert row["title"] == "痛点钩子"
    assert hits


@pytest.mark.asyncio
async def test_knowledge_base_full():
    from memory.knowledge_base import KnowledgeBase

    kb = KnowledgeBase()
    product = await kb.ingest_hot_product(
        {"platform": "douyin", "name": "Phase1测试商品", "price": 39.9, "sales": 800}
    )
    assert product
    ctx = await kb.retrieve_context(query="测试商品", platform="douyin")
    assert ctx["query"] == "测试商品"
    assert "hot_products" in ctx
    decision = await kb.log_decision(
        agent_name="perception",
        decision_type="scrape_products",
        confidence=0.9,
    )
    assert decision


def test_memory_public_exports():
    from memory import (
        BannedWordsFilter,
        KnowledgeBase,
        SOPDocument,
        VectorStore,
    )

    assert VectorStore.COLLECTIONS
    assert BannedWordsFilter
    assert SOPDocument
    assert KnowledgeBase
