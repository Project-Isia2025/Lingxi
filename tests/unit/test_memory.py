"""记忆模块单元测试。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


@pytest.mark.asyncio
async def test_vector_store_add_search():
    from memory.vector_store import VectorStore

    vs = VectorStore()
    await vs.add("scripts", "爆款护肤脚本模板", {"id": "s1", "title": "护肤"})
    results = await vs.search("scripts", "护肤", limit=3)
    assert len(results) >= 1


def test_banned_words_filter():
    from memory.banned_words import BannedWordsFilter

    f = BannedWordsFilter()
    hits = f.check("这是最好的产品，国家级品质")
    assert "最好" in hits or "国家级" in hits
    sanitized = f.sanitize("最好的")
    assert "****" in sanitized
