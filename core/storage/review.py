"""Storage domain: review."""
from __future__ import annotations

import json
import os
from typing import Any

import bootstrap

from core.storage._common import _connect, _now, init_storage

def enqueue_review(
    *,
    review_id: str,
    run_id: str,
    video_path: str,
    script: str,
    title: str = "",
    payload: dict[str, Any] | None = None,
) -> None:
    init_storage()
    ts = _now()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO review_queue (
                review_id, run_id, video_path, script, title, status,
                payload_json, created_ts, updated_ts
            ) VALUES (?, ?, ?, ?, ?, 'pending_review', ?, ?, ?)
            """,
            (
                review_id,
                run_id,
                video_path,
                script,
                title,
                json.dumps(payload or {}, ensure_ascii=False),
                ts,
                ts,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_review_item(review_id: str) -> dict[str, Any] | None:
    init_storage()
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM review_queue WHERE review_id=?", (review_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["payload"] = json.loads(d.pop("payload_json") or "{}")
        except Exception:
            d["payload"] = {}
        return d
    finally:
        conn.close()


def list_review_queue(*, status: str = "", limit: int = 50) -> list[dict[str, Any]]:
    init_storage()
    conn = _connect()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM review_queue WHERE status=? ORDER BY created_ts DESC LIMIT ?",
                (status, max(1, limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM review_queue ORDER BY created_ts DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            try:
                d["payload"] = json.loads(d.pop("payload_json") or "{}")
            except Exception:
                d["payload"] = {}
            out.append(d)
        return out
    finally:
        conn.close()


def update_review_status(
    *,
    review_id: str,
    status: str,
    reject_reason: str = "",
    feishu_msg_id: str = "",
) -> bool:
    init_storage()
    ts = _now()
    conn = _connect()
    try:
        cur = conn.execute(
            """
            UPDATE review_queue
            SET status=?, reject_reason=?, feishu_msg_id=?, updated_ts=?, reviewed_ts=?
            WHERE review_id=?
            """,
            (status, reject_reason, feishu_msg_id, ts, ts, review_id),
        )
        conn.commit()
        return int(cur.rowcount or 0) > 0
    finally:
        conn.close()


def delete_review(review_id: str) -> bool:
    init_storage()
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM review_queue WHERE review_id=?", (review_id,))
        conn.commit()
        return int(cur.rowcount or 0) > 0
    finally:
        conn.close()


def delete_all_pending_reviews() -> dict[str, int]:
    init_storage()
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM review_queue WHERE status='pending_review'")
        conn.commit()
        return {"deleted": int(cur.rowcount or 0)}
    finally:
        conn.close()


def purge_reviews(*, statuses: tuple[str, ...], older_than_sec: int) -> dict[str, int]:
    """删除指定状态且 reviewed_ts/updated_ts 早于阈值的审核记录。"""
    init_storage()
    if not statuses:
        return {"deleted": 0}
    cutoff = _now() - max(0, int(older_than_sec))
    placeholders = ",".join("?" for _ in statuses)
    conn = _connect()
    try:
        cur = conn.execute(
            f"""
            DELETE FROM review_queue
            WHERE status IN ({placeholders})
              AND COALESCE(NULLIF(reviewed_ts, 0), updated_ts, created_ts) < ?
            """,
            (*statuses, cutoff),
        )
        conn.commit()
        return {"deleted": int(cur.rowcount or 0), "cutoff_ts": cutoff}
    finally:
        conn.close()


