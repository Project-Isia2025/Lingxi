"""Alembic 迁移封装 — 与 schema_meta 同步。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import bootstrap

bootstrap.ensure_paths()

_ALEMBIC_INI = bootstrap.project_root() / "alembic.ini"
_REVISION_VERSION = {
    "001_baseline": "1",
    "002_metrics_run_index": "2",
}


def migrations_enabled() -> bool:
    return os.environ.get("DB_MIGRATE_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def _sync_db_path_for_migrate() -> None:
    import sys

    import core.db as db

    storage_mod = sys.modules.get("core.storage")
    if storage_mod is not None:
        patched = getattr(storage_mod, "DB_PATH", None)
        if patched is not None and patched is not db.DB_PATH:
            db.DB_PATH = patched


def sqlite_url() -> str:
    _sync_db_path_for_migrate()
    from core.db import DB_PATH

    path = Path(DB_PATH).resolve()
    return f"sqlite:///{path.as_posix()}"


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", sqlite_url())
    return cfg


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _has_legacy_schema(conn) -> bool:
    return _table_exists(conn, "kb_items") or _table_exists(conn, "publish_queue")


def _has_alembic_version(conn) -> bool:
    return _table_exists(conn, "alembic_version")


def sync_schema_meta(revision: str) -> None:
    from core.db import connect

    version = _REVISION_VERSION.get(revision, revision)
    conn = connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', ?)",
            (version,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('alembic_revision', ?)",
            (revision,),
        )
        conn.commit()
    finally:
        conn.close()


def current_revision() -> str | None:
    if not migrations_enabled():
        from core.db import schema_version

        return schema_version() or None

    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    engine = create_engine(sqlite_url())
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            rev = ctx.get_current_revision()
            if rev:
                return rev
    finally:
        engine.dispose()

    from core.db import connect

    try:
        conn = connect()
        if not _has_alembic_version(conn) and _has_legacy_schema(conn):
            row = conn.execute(
                "SELECT value FROM schema_meta WHERE key='alembic_revision'"
            ).fetchone()
            conn.close()
            return str(row[0]) if row else "001_baseline (legacy)"
        conn.close()
    except Exception:
        pass
    return None


def stamp_revision(revision: str) -> None:
    from alembic import command

    command.stamp(_alembic_config(), revision)
    sync_schema_meta(revision)


def upgrade_head() -> str | None:
    from alembic import command

    _sync_db_path_for_migrate()
    from core.db import connect

    conn = connect()
    try:
        legacy = _has_legacy_schema(conn) and not _has_alembic_version(conn)
    finally:
        conn.close()

    cfg = _alembic_config()
    if legacy:
        from alembic import command as alembic_command

        alembic_command.stamp(cfg, "001_baseline")
        sync_schema_meta("001_baseline")

    command.upgrade(cfg, "head")
    rev = current_revision()
    if rev and rev != "001_baseline (legacy)":
        sync_schema_meta(rev)
    return rev


def ensure_migrated() -> dict[str, Any]:
    """启动/初始化时调用：升级至 head 并同步 schema_meta。"""
    if not migrations_enabled():
        from core.db import connect
        from core.schema_sql import BASELINE_DDL

        conn = connect()
        try:
            conn.executescript(BASELINE_DDL)
            conn.execute(
                "INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('version', '1')"
            )
            conn.commit()
        finally:
            conn.close()
        from core.db import schema_version

        return {"ok": True, "mode": "legacy_ddl", "revision": schema_version()}

    rev = upgrade_head()
    from core.db import schema_version

    return {
        "ok": True,
        "mode": "alembic",
        "revision": rev,
        "schema_version": schema_version(),
    }


def migration_status() -> dict[str, Any]:
    from core.db import DB_PATH, schema_version

    return {
        "ok": True,
        "enabled": migrations_enabled(),
        "db_path": str(DB_PATH),
        "alembic_revision": current_revision(),
        "schema_version": schema_version(),
        "head": "002_metrics_run_index",
    }
