"""Storage domain: kb."""
from __future__ import annotations

import json
import os
from typing import Any

import bootstrap

from core.storage._common import _connect, _now, init_storage

def kb_search(*, query: str, library: str = "", limit: int = 5) -> list[dict[str, Any]]:
    init_storage()
    q = (query or "").strip().lower()
    conn = _connect()
    try:
        if library:
            rows = conn.execute(
                """
                SELECT id, library, title, body, tags, platform, roi_score
                FROM kb_items WHERE enabled=1 AND library=?
                ORDER BY roi_score DESC, updated_ts DESC LIMIT 80
                """,
                (library,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, library, title, body, tags, platform, roi_score
                FROM kb_items WHERE enabled=1
                ORDER BY roi_score DESC, updated_ts DESC LIMIT 120
                """
            ).fetchall()
        hits: list[tuple[float, dict[str, Any]]] = []
        tokens = [t for t in q.split() if len(t) >= 2]
        for r in rows:
            blob = f"{r['title']} {r['body']} {r['tags']}".lower()
            score = float(r["roi_score"] or 0) * 0.1
            for t in tokens:
                if t in blob:
                    score += 2.0
            if score > 0 or not tokens:
                hits.append((score, dict(r)))
        hits.sort(key=lambda x: x[0], reverse=True)
        return [h[1] for h in hits[: max(1, limit)]]
    finally:
        conn.close()


def kb_upsert(*, library: str, title: str, body: str, tags: str = "", platform: str = "all") -> int:
    init_storage()
    conn = _connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO kb_items (library, title, body, tags, platform, updated_ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (library, title, body, tags, platform, _now()),
        )
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        conn.close()


def seed_kb_if_empty() -> None:
    init_storage()
    conn = _connect()
    try:
        n = conn.execute("SELECT COUNT(*) FROM kb_items").fetchone()[0]
        if n > 0:
            return
    finally:
        conn.close()

    seeds = [
        ("story", "敏感肌修复真实案例", "客户Lisa用28天改善屏障，关键三步：温和清洁、精简护肤、防晒。", "护肤,案例", "douyin"),
        ("faq", "产品适合什么肤质", "适合敏感肌、干燥肌；油痘肌建议先做局部测试。", "护肤,faq", "all"),
        ("hotspot", "夏季防晒趋势", "物理防晒+养肤成分成为短视频热门话题。", "防晒,热点", "douyin"),
        ("sales_script", "私信领取话术", "你好，看到你对护肤感兴趣，回复「资料」领取避坑清单。", "私信,转化", "all"),
        ("sop", "口播开场SOP", "3秒钩子：痛点提问 → 共鸣场景 → 给出解决方案预告。", "口播,sop", "all"),
    ]
    for lib, title, body, tags, plat in seeds:
        kb_upsert(library=lib, title=title, body=body, tags=tags, platform=plat)


def load_forbidden_words() -> list[dict[str, Any]]:
    init_storage()
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT word, word_type, replace_word FROM forbidden_words ORDER BY id"
        ).fetchall()
        if rows:
            return [dict(r) for r in rows]
    finally:
        conn.close()

    defaults = [
        ("最好", "forbidden", "优选"),
        ("第一", "forbidden", "领先"),
        ("根治", "forbidden", "改善"),
        ("加微信", "drain", "私信我"),
    ]
    conn = _connect()
    try:
        for w, wt, rep in defaults:
            conn.execute(
                "INSERT OR IGNORE INTO forbidden_words (word, word_type, replace_word) VALUES (?,?,?)",
                (w, wt, rep),
            )
        conn.commit()
        rows = conn.execute(
            "SELECT word, word_type, replace_word FROM forbidden_words"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def load_brand_config() -> dict[str, Any]:
    path = bootstrap.project_root() / "data" / "brand.json"
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "brand_name": "矩阵品牌",
        "industry": "通用",
        "cta_text": "私信回复「资料」领取完整版",
        "forbidden_words": [],
    }


def kb_boost_roi(*, item_id: int, delta: float = 0.1) -> None:
    init_storage()
    conn = _connect()
    try:
        conn.execute(
            "UPDATE kb_items SET roi_score = MIN(10, roi_score + ?), updated_ts = ? WHERE id = ?",
            (delta, _now(), item_id),
        )
        conn.commit()
    finally:
        conn.close()


def kb_list_recent(*, tag_contains: str = "", title_prefix: str = "", limit: int = 30) -> list[dict[str, Any]]:
    init_storage()
    conn = _connect()
    try:
        sql = """
            SELECT id, library, title, body, tags, platform, roi_score, updated_ts
            FROM kb_items
            WHERE 1=1
        """
        params: list[Any] = []
        if tag_contains:
            sql += " AND tags LIKE ?"
            params.append(f"%{tag_contains}%")
        if title_prefix:
            sql += " AND title LIKE ?"
            params.append(f"{title_prefix}%")
        sql += " ORDER BY updated_ts DESC LIMIT ?"
        params.append(max(1, limit))
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_episodic(*, run_id: str, agent: str, observation: str, action: str, payload: dict | None = None) -> None:
    init_storage()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO episodic_memory (run_id, agent, observation, action, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, agent, observation, action, json.dumps(payload or {}, ensure_ascii=False), _now()),
        )
        conn.commit()
    finally:
        conn.close()


def list_episodic_recent(*, action: str = "", limit: int = 30) -> list[dict[str, Any]]:
    init_storage()
    conn = _connect()
    try:
        if action:
            rows = conn.execute(
                """
                SELECT run_id, agent, observation, action, payload_json, created_at
                FROM episodic_memory WHERE action=?
                ORDER BY created_at DESC LIMIT ?
                """,
                (action, max(1, limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT run_id, agent, observation, action, payload_json, created_at
                FROM episodic_memory
                ORDER BY created_at DESC LIMIT ?
                """,
                (max(1, limit),),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d.pop("payload_json") or "{}")
            except Exception:
                d["payload"] = {}
            out.append(d)
        return out
    finally:
        conn.close()


def find_similar_script(text: str, *, threshold: float = 0.72) -> dict[str, Any] | None:
    import re

def save_script_history(
    *,
    script: str,
    dedupe_hash: str,
    run_id: str = "",
    keyword: str = "",
    platform: str = "",
) -> None:
    init_storage()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO script_history (run_id, dedupe_hash, script, keyword, platform, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, dedupe_hash, script, keyword, platform, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def list_script_history(*, limit: int = 50) -> list[dict[str, Any]]:
    init_storage()
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, run_id, dedupe_hash, script, keyword, platform, created_at FROM script_history ORDER BY id DESC LIMIT ?",
            (max(1, limit),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


