"""工作流运行持久化（本矩阵项目独立 SQLite）。"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import bootstrap


def _db_path() -> Path:
    raw = os.environ.get("MATRIX_DB_PATH", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return bootstrap.project_root() / "data" / "matrix_agent.db"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table() -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orchestrator_runs (
                run_id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL DEFAULT '',
                stage TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                updated_ts INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_orchestrator_runs_org
            ON orchestrator_runs(org_id, updated_ts DESC)
            """
        )
        conn.commit()
    finally:
        conn.close()


def save_run(ctx_dict: dict[str, Any]) -> None:
    run_id = str(ctx_dict.get("run_id") or "").strip()
    if not run_id:
        return
    _ensure_table()
    goal = ctx_dict.get("goal") or {}
    org_id = str(goal.get("org_id") or "").strip()
    stage = str(ctx_dict.get("stage") or "")
    status = str(ctx_dict.get("status") or "pending")
    updated = int(time.time())
    blob = json.dumps(ctx_dict, ensure_ascii=False, default=str)
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO orchestrator_runs (run_id, org_id, stage, status, updated_ts, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
              org_id=excluded.org_id,
              stage=excluded.stage,
              status=excluded.status,
              updated_ts=excluded.updated_ts,
              payload_json=excluded.payload_json
            """,
            (run_id, org_id, stage, status, updated, blob),
        )
        conn.commit()
    finally:
        conn.close()


def load_run(run_id: str) -> dict[str, Any] | None:
    rid = str(run_id or "").strip()
    if not rid:
        return None
    _ensure_table()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT payload_json FROM orchestrator_runs WHERE run_id=?",
            (rid,),
        ).fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        return data if isinstance(data, dict) else None
    finally:
        conn.close()


def list_runs(*, org_id: str = "", limit: int = 30) -> list[dict[str, Any]]:
    _ensure_table()
    limit = max(1, min(int(limit or 30), 100))
    conn = _connect()
    try:
        if org_id:
            rows = conn.execute(
                """
                SELECT run_id, org_id, stage, status, updated_ts
                FROM orchestrator_runs
                WHERE org_id=?
                ORDER BY updated_ts DESC
                LIMIT ?
                """,
                (org_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT run_id, org_id, stage, status, updated_ts
                FROM orchestrator_runs
                ORDER BY updated_ts DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "run_id": r[0],
                "org_id": r[1],
                "stage": r[2],
                "status": r[3],
                "updated_ts": r[4],
            }
            for r in rows
        ]
    finally:
        conn.close()


def delete_run(run_id: str) -> bool:
    rid = str(run_id or "").strip()
    if not rid:
        return False
    _ensure_table()
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM orchestrator_runs WHERE run_id=?", (rid,))
        conn.commit()
        return int(cur.rowcount or 0) > 0
    finally:
        conn.close()


def purge_runs(*, statuses: tuple[str, ...], older_than_sec: int) -> dict[str, int]:
    _ensure_table()
    if not statuses:
        return {"deleted": 0}
    cutoff = int(time.time()) - max(0, int(older_than_sec))
    placeholders = ",".join("?" for _ in statuses)
    conn = _connect()
    try:
        cur = conn.execute(
            f"""
            DELETE FROM orchestrator_runs
            WHERE status IN ({placeholders}) AND updated_ts < ?
            """,
            (*statuses, cutoff),
        )
        conn.commit()
        return {"deleted": int(cur.rowcount or 0), "cutoff_ts": cutoff}
    finally:
        conn.close()


def delete_all_runs_with_status(*, statuses: tuple[str, ...]) -> dict[str, int]:
    _ensure_table()
    if not statuses:
        return {"deleted": 0}
    placeholders = ",".join("?" for _ in statuses)
    conn = _connect()
    try:
        cur = conn.execute(
            f"DELETE FROM orchestrator_runs WHERE status IN ({placeholders})",
            statuses,
        )
        conn.commit()
        return {"deleted": int(cur.rowcount or 0)}
    finally:
        conn.close()
