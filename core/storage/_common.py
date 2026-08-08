"""Storage shared DB helpers."""
from __future__ import annotations

import sys

from core.db import DB_PATH, now_ts as _now


def _sync_db_path() -> None:
    import core.db as db

    target = db.DB_PATH
    storage_mod = sys.modules.get("core.storage")
    if storage_mod is not None:
        patched = getattr(storage_mod, "DB_PATH", None)
        if patched is not None:
            target = patched
    if db.DB_PATH != target:
        db.DB_PATH = target


def init_storage() -> None:
    _sync_db_path()
    import core.db as db

    db.init_storage()


def _connect():
    _sync_db_path()
    import core.db as db

    return db.connect()
