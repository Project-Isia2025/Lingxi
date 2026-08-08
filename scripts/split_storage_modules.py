#!/usr/bin/env python
"""一次性脚本：将 core/storage/__init__.py 拆分为领域模块。"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src_path = ROOT / "core" / "storage" / "__init__.py"
src = src_path.read_text(encoding="utf-8")
tree = ast.parse(src)
funcs = {n.name: n.lineno for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
lines = src.splitlines()

groups = {
    "kb": [
        "kb_search",
        "kb_upsert",
        "seed_kb_if_empty",
        "load_forbidden_words",
        "load_brand_config",
        "kb_boost_roi",
        "kb_list_recent",
        "save_episodic",
        "list_episodic_recent",
        "find_similar_script",
        "save_script_history",
        "list_script_history",
    ],
    "metrics": [
        "metrics_record",
        "metrics_summary",
        "metrics_latest",
        "metrics_for_run",
        "metrics_daily_series",
        "metrics_export_rows",
        "alert_was_sent_recently",
        "record_alert_sent",
        "count_alert_sent_log",
        "purge_expired_alert_logs",
    ],
    "review": [
        "enqueue_review",
        "get_review_item",
        "list_review_queue",
        "update_review_status",
    ],
    "monitors": [
        "schedule_post_monitor",
        "list_due_post_monitors",
        "update_post_monitor",
        "list_post_monitors",
    ],
    "ad": [
        "save_ad_campaign",
        "get_ad_campaign_by_run",
        "update_ad_campaign_report",
        "list_ad_campaigns",
    ],
    "publish": [
        "update_publish_queue_priority",
        "save_execution_job",
        "get_publish_state",
        "set_publish_state",
        "append_publish_log",
        "upsert_publish_account",
        "list_publish_accounts",
        "pick_publish_account",
        "enqueue_publish",
        "list_publish_queue",
        "get_publish_queue_job",
        "requeue_publish_job",
        "list_publish_queue_items",
        "update_publish_queue_schedule",
        "update_publish_queue_status",
        "list_publish_log",
    ],
}

ordered = sorted(funcs.items(), key=lambda x: x[1])
name_to_span: dict[str, tuple[int, int]] = {}
for i, (name, start) in enumerate(ordered):
    end = ordered[i + 1][1] - 1 if i + 1 < len(ordered) else len(lines)
    name_to_span[name] = (start, end)

module_header = '''"""Storage domain: {name}."""
from __future__ import annotations

import json
import os
from typing import Any

import bootstrap

from core.storage._common import _connect, _now, init_storage

'''

out_dir = ROOT / "core" / "storage"
for mod, fnames in groups.items():
    chunks: list[str] = []
    for fn in fnames:
        if fn not in name_to_span:
            raise SystemExit(f"missing function in source: {fn}")
        s, e = name_to_span[fn]
        chunks.extend(lines[s - 1 : e])
    (out_dir / f"{mod}.py").write_text(module_header.format(name=mod) + "\n".join(chunks) + "\n", encoding="utf-8")

common_parts: list[str] = []
for name in ("_sync_db_path", "init_storage", "_connect"):
    s, e = name_to_span[name]
    common_parts.extend(lines[s - 1 : e])

common = (
    '"""Storage shared DB helpers."""\n'
    "from __future__ import annotations\n\n"
    "from core.db import DB_PATH, now_ts as _now\n\n"
    + "\n".join(common_parts)
    + "\n"
)
(out_dir / "_common.py").write_text(common, encoding="utf-8")

init_body = '''"""SQLite storage package — backward-compatible re-exports."""
from __future__ import annotations

from core.storage._common import DB_PATH, init_storage, _connect, _now
from core.storage.ad import *
from core.storage.kb import *
from core.storage.metrics import *
from core.storage.monitors import *
from core.storage.publish import *
from core.storage.review import *

__all__ = [
    "DB_PATH",
    "init_storage",
    "_connect",
    "_now",
]
'''
(out_dir / "__init__.py").write_text(init_body, encoding="utf-8")
print("split complete")
