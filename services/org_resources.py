"""多 org 发布账号与库存资源过滤。"""
from __future__ import annotations

from typing import Any

from services.tenant import normalize_org_id, org_isolation_enabled


def account_org_id(row: dict[str, Any]) -> str:
    return normalize_org_id(str(row.get("org_id") or ""))


def product_org_id(row: dict[str, Any]) -> str:
    return normalize_org_id(str(row.get("org_id") or ""))


def filter_accounts_by_org(
    accounts: list[dict[str, Any]],
    org_id: str = "",
) -> list[dict[str, Any]]:
    oid = normalize_org_id(org_id)
    if not org_isolation_enabled() or not oid:
        return accounts
    out = []
    for row in accounts:
        aoid = account_org_id(row)
        if not aoid or aoid == oid:
            out.append(row)
    return out


def filter_products_by_org(
    products: list[dict[str, Any]],
    org_id: str = "",
) -> list[dict[str, Any]]:
    oid = normalize_org_id(org_id)
    if not org_isolation_enabled() or not oid:
        return products
    out = []
    for row in products:
        poid = product_org_id(row)
        if not poid or poid == oid:
            out.append(row)
    return out
