"""内容去重：与历史脚本库比对相似度。"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from core.storage import find_similar_script, save_script_history


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip().lower())


def dedupe_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode()).hexdigest()[:16]


def char_ngrams(text: str, n: int = 3) -> set[str]:
    s = normalize(text)
    if len(s) < n:
        return {s} if s else set()
    return {s[i : i + n] for i in range(len(s) - n + 1)}


def similarity(a: str, b: str) -> float:
    ga, gb = char_ngrams(a), char_ngrams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def check_duplicate(script: str, *, run_id: str = "") -> dict[str, Any]:
    h = dedupe_hash(script)
    similar = find_similar_script(script, threshold=0.72)
    is_dup = bool(similar)
    return {
        "dedupe_hash": h,
        "duplicate": is_dup,
        "similar_script": similar,
        "similarity": similar.get("similarity") if similar else 0.0,
        "recommendation": "建议换角度或增加新案例" if is_dup else "内容独特性良好",
    }


def record_script(script: str, *, run_id: str = "", keyword: str = "", platform: str = "") -> None:
    save_script_history(
        script=script,
        dedupe_hash=dedupe_hash(script),
        run_id=run_id,
        keyword=keyword,
        platform=platform,
    )
