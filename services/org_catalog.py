"""已知 org_id 目录（从队列/监控/账号聚合）。"""
from __future__ import annotations

import os
from typing import Any

from services.tenant import item_org_id, normalize_org_id, org_isolation_enabled


def _collect_from_items(items: list[dict[str, Any]], orgs: set[str]) -> None:
    for item in items:
        oid = item_org_id(item)
        if not oid:
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            oid = normalize_org_id(str(payload.get("org_id") or ""))
        if oid:
            orgs.add(oid)


def list_org_ids(*, limit: int = 50) -> list[str]:
    orgs: set[str] = set()
    default = normalize_org_id(os.environ.get("DEFAULT_ORG_ID", ""))
    if default:
        orgs.add(default)

    try:
        from core.storage import list_post_monitors, list_publish_queue_items

        _collect_from_items(list_publish_queue_items(limit=300), orgs)
        _collect_from_items(list_post_monitors(limit=200), orgs)
    except Exception:
        pass

    try:
        from services.publish.scheduler import list_accounts

        for row in list_accounts() or []:
            oid = normalize_org_id(str(row.get("org_id") or ""))
            if oid:
                orgs.add(oid)
    except Exception:
        pass

    out = sorted(orgs)
    return out[: max(1, limit)]


def org_catalog_status() -> dict[str, Any]:
    orgs = list_org_ids()
    return {
        "ok": True,
        "isolation_enabled": org_isolation_enabled(),
        "orgs": orgs,
        "count": len(orgs),
    }
