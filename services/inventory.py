"""店铺库存数据源。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import bootstrap


def inventory_path() -> Path:
    custom = bootstrap.project_root() / "data" / "inventory.json"
    if custom.is_file():
        return custom
    return bootstrap.project_root() / "data" / "inventory.example.json"


def load_inventory() -> list[dict[str, Any]]:
    path = inventory_path()
    if not path.is_file():
        return [{
            "sku": "A-MASK-001",
            "name": "A款面膜",
            "keyword": "A面膜",
            "stock": 2000,
            "priority": 100,
            "enabled": True,
        }]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return [x for x in raw.get("products") or [] if isinstance(x, dict)]
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
    except Exception:
        pass
    return []


def list_products(*, min_stock: int = 1, org_id: str = "") -> list[dict[str, Any]]:
    from services.org_resources import filter_products_by_org

    out = []
    for p in load_inventory():
        if not p.get("enabled", True):
            continue
        stock = int(p.get("stock") or 0)
        if stock < min_stock:
            continue
        out.append(p)
    out = filter_products_by_org(out, org_id)
    out.sort(key=lambda x: (-int(x.get("priority") or 0), -int(x.get("stock") or 0)))
    return out


def get_primary_product(*, org_id: str = "") -> dict[str, Any]:
    products = list_products(org_id=org_id)
    if not products:
        return {"ok": False, "error": "no_inventory", "org_id": org_id}
    return {"ok": True, "product": products[0], "products": products, "org_id": org_id}


def get_product_by_sku(sku: str) -> dict[str, Any] | None:
    for p in load_inventory():
        if str(p.get("sku") or "") == sku:
            return p
    return None
