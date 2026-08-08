"""多租户 org_id 隔离（轻量：payload 存储 + 列表过滤）。"""
from __future__ import annotations

import os
from typing import Any


def org_isolation_enabled() -> bool:
    return os.environ.get("ORG_ISOLATION_ENABLED", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def normalize_org_id(org_id: str | None) -> str:
    return (org_id or "").strip()


def default_org_id() -> str:
    return normalize_org_id(os.environ.get("DEFAULT_ORG_ID", ""))


def item_org_id(item: dict[str, Any]) -> str:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    for key in ("org_id",):
        val = normalize_org_id(str((payload or {}).get(key) or item.get(key) or ""))
        if val:
            return val
    return ""


def filter_by_org(items: list[dict[str, Any]], org_id: str = "") -> list[dict[str, Any]]:
    oid = normalize_org_id(org_id)
    if not org_isolation_enabled() or not oid:
        return items
    out = []
    for item in items:
        ioid = item_org_id(item)
        if not ioid or ioid == oid:
            out.append(item)
    return out


def assert_org_access(item: dict[str, Any], org_id: str = "") -> tuple[bool, str]:
    oid = normalize_org_id(org_id)
    if not org_isolation_enabled() or not oid:
        return True, ""
    ioid = item_org_id(item)
    if ioid and ioid != oid:
        return False, "org_access_denied"
    return True, ""


def attach_org(payload: dict[str, Any] | None, org_id: str = "") -> dict[str, Any]:
    out = dict(payload or {})
    oid = normalize_org_id(org_id) or default_org_id()
    if oid:
        out["org_id"] = oid
    return out
