"""Storage domain: monitors."""
from __future__ import annotations

import json
import os
from typing import Any

import bootstrap

from core.storage._common import _connect, _now, init_storage

def schedule_post_monitor(
    *,
    monitor_id: str,
    run_id: str,
    platform: str,
    post_url: str,
    job_id: str = "",
    due_ts: int,
    payload: dict[str, Any] | None = None,
) -> None:
    init_storage()
    ts = _now()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO post_publish_monitors (
                monitor_id, run_id, platform, post_url, job_id, status,
                due_ts, payload_json, created_ts, updated_ts
            ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
            """,
            (
                monitor_id,
                run_id,
                platform,
                post_url,
                job_id,
                int(due_ts),
                json.dumps(payload or {}, ensure_ascii=False),
                ts,
                ts,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_due_post_monitors(*, limit: int = 10) -> list[dict[str, Any]]:
    init_storage()
    now = _now()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT * FROM post_publish_monitors
            WHERE status='pending' AND due_ts <= ?
            ORDER BY due_ts ASC LIMIT ?
            """,
            (now, max(1, limit)),
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


def update_post_monitor(
    *,
    monitor_id: str,
    status: str,
    completion_rate: float | None = None,
    ctr: float | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    init_storage()
    ts = _now()
    conn = _connect()
    try:
        if payload is not None:
            conn.execute(
                """
                UPDATE post_publish_monitors
                SET status=?, completion_rate=COALESCE(?, completion_rate),
                    ctr=COALESCE(?, ctr), payload_json=?, updated_ts=?
                WHERE monitor_id=?
                """,
                (
                    status,
                    completion_rate,
                    ctr,
                    json.dumps(payload, ensure_ascii=False),
                    ts,
                    monitor_id,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE post_publish_monitors
                SET status=?, completion_rate=COALESCE(?, completion_rate),
                    ctr=COALESCE(?, ctr), updated_ts=?
                WHERE monitor_id=?
                """,
                (status, completion_rate, ctr, ts, monitor_id),
            )
        conn.commit()
    finally:
        conn.close()


def list_post_monitors(*, status: str = "", limit: int = 50) -> list[dict[str, Any]]:
    init_storage()
    conn = _connect()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM post_publish_monitors WHERE status=? ORDER BY updated_ts DESC LIMIT ?",
                (status, max(1, limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM post_publish_monitors ORDER BY updated_ts DESC LIMIT ?",
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


