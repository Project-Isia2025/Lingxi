"""Alembic 迁移 + schema_meta 测试。"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


def _patch_db(db_path: Path):
    import core.db as db_mod
    import core.storage as storage_mod

    db_mod.DB_PATH = db_path
    storage_mod.DB_PATH = db_path
    return db_mod, storage_mod


def test_fresh_db_migrates_to_head():
    from core.db import alembic_revision, init_storage, schema_version
    from core.migrate import migration_status

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "fresh.db"
        _patch_db(db)
        with mock.patch.dict(os.environ, {"DB_MIGRATE_ENABLED": "1"}, clear=False):
            from core.migrate import ensure_migrated

            out = ensure_migrated()
            assert out["ok"] is True
            assert out["mode"] == "alembic"
            assert schema_version() == "2"
            assert alembic_revision() == "002_metrics_run_index"
            status = migration_status()
            assert status["enabled"] is True
            assert status["head"] == "002_metrics_run_index"
            assert status["schema_version"] == "2"


def test_legacy_db_auto_stamp_and_upgrade():
    from core.db import connect, init_storage, schema_version
    from core.schema_sql import BASELINE_DDL

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "legacy.db"
        _patch_db(db)
        conn = connect()
        conn.executescript(BASELINE_DDL)
        conn.execute(
            "INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('version', '1')"
        )
        conn.commit()
        conn.close()

        with mock.patch.dict(os.environ, {"DB_MIGRATE_ENABLED": "1"}, clear=False):
            init_storage()
            assert schema_version() == "2"

        conn = connect()
        row = conn.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "002_metrics_run_index"


def test_legacy_ddl_mode_when_migrations_disabled():
    from core.db import init_storage, schema_version
    from core.migrate import ensure_migrated

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "legacy_mode.db"
        _patch_db(db)
        with mock.patch.dict(os.environ, {"DB_MIGRATE_ENABLED": "0"}, clear=False):
            out = ensure_migrated()
            assert out["mode"] == "legacy_ddl"
            assert schema_version() == "1"

        conn = __import__("core.db", fromlist=["connect"]).connect()
        has_alembic = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        ).fetchone()
        conn.close()
        assert has_alembic is None


def test_metrics_run_index_exists_after_migration():
    from core.db import connect, init_storage

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "indexed.db"
        _patch_db(db)
        with mock.patch.dict(os.environ, {"DB_MIGRATE_ENABLED": "1"}, clear=False):
            init_storage()

        conn = connect()
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_content_metrics_run'"
        ).fetchone()
        conn.close()
        assert row is not None
