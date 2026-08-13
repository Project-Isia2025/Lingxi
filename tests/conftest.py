"""Pytest 全局 fixture — 测试环境隔离。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 强制测试环境（覆盖 shell / local.env，bootstrap 不会覆盖已存在 key）
for _k, _v in {
    "WORKER_BACKEND": "thread",
    "WORKER_LEADER_LOCK_ENABLED": "0",
    "ENVIRONMENT": "development",
    "API_AUTH_ENABLED": "0",
    "DB_MIGRATE_ENABLED": "1",
    "REDIS_HOST": "localhost",
    "REDIS_PORT": "6379",
}.items():
    os.environ[_k] = _v

import bootstrap

bootstrap.ensure_paths()


@pytest.fixture(scope="session", autouse=True)
def isolated_sqlite_db() -> Path:
    """会话级临时 SQLite，避免污染 data/matrix_agent.db。"""
    db_dir = ROOT / "data" / ".pytest"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "pytest_matrix.db"
    for extra in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        if extra.exists():
            try:
                extra.unlink()
            except OSError:
                pass

    import core.db as db_mod
    import core.storage as storage_mod

    orig_db = db_mod.DB_PATH
    orig_storage = storage_mod.DB_PATH
    db_mod.DB_PATH = db_path
    storage_mod.DB_PATH = db_path

    from core.storage import init_storage

    init_storage()
    yield db_path

    db_mod.DB_PATH = orig_db
    storage_mod.DB_PATH = orig_storage


@pytest.fixture(autouse=True)
def reset_worker_health_cache() -> None:
    """Celery 在线探测带缓存，用例间清零。"""
    try:
        import infra.worker_health as wh

        wh._CACHE["ts"] = 0.0
        wh._CACHE["online"] = False
    except Exception:
        pass
    yield
