"""Campaign 活动状态存储。"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import bootstrap

_STORE_PATH = bootstrap.project_root() / "data" / "state" / "campaigns.json"
_memory: dict[str, dict] = {}


def _load() -> dict[str, dict]:
    global _memory
    if _memory:
        return _memory
    if _STORE_PATH.is_file():
        try:
            _memory = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        except Exception:
            _memory = {}
    return _memory


def _save() -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(_load(), ensure_ascii=False, indent=2), encoding="utf-8")


def create(campaign_id: str, *, goal: str, platform: str, budget: float) -> dict:
    row = {
        "campaign_id": campaign_id,
        "status": "started",
        "goal": goal,
        "platform": platform,
        "budget": budget,
        "state": None,
        "error": None,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }
    store = _load()
    store[campaign_id] = row
    _save()
    return row


def update(campaign_id: str, **fields) -> dict | None:
    store = _load()
    row = store.get(campaign_id)
    if row is None:
        return None
    row.update(fields)
    row["updated_at"] = int(time.time())
    store[campaign_id] = row
    _save()
    return row


def get(campaign_id: str) -> dict | None:
    return _load().get(campaign_id)


def list_campaigns(limit: int = 20) -> list[dict]:
    rows = sorted(_load().values(), key=lambda x: x.get("updated_at", 0), reverse=True)
    return rows[:limit]
