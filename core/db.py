"""SQLite 连接与 Schema 初始化。"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import bootstrap

DB_PATH = bootstrap.project_root() / "data" / "matrix_agent.db"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
    except Exception:
        pass
    return conn


def now_ts() -> int:
    return int(time.time())


def init_storage() -> None:
    from core.migrate import ensure_migrated

    ensure_migrated()


def schema_version() -> str:
    try:
        conn = connect()
        row = conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()
        conn.close()
        return str(row[0]) if row else "0"
    except Exception:
        return "0"


def alembic_revision() -> str:
    try:
        conn = connect()
        row = conn.execute("SELECT value FROM schema_meta WHERE key='alembic_revision'").fetchone()
        conn.close()
        return str(row[0]) if row else ""
    except Exception:
        return ""
