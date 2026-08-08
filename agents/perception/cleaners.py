"""数据清洗。"""
from __future__ import annotations

import re
from typing import Any


def parse_price(raw: str | float | None) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    m = re.search(r"[\d.]+", str(raw).replace(",", ""))
    return float(m.group()) if m else 0.0


def clean_products(products: list[dict], platform: str) -> list[dict]:
    seen: set[str] = set()
    cleaned = []
    for p in products:
        name = str(p.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        cleaned.append(
            {
                "name": name,
                "price": parse_price(p.get("price")),
                "sales": p.get("sales"),
                "url": p.get("url"),
                "platform": platform,
            }
        )
    return cleaned
