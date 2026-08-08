"""选品引擎。"""
from __future__ import annotations

from typing import Any

from memory.vector_store import VectorStore


class ProductSelector:
    WEIGHTS = {
        "trend_score": 0.30,
        "competition": 0.20,
        "profit_margin": 0.25,
        "seasonality": 0.15,
        "platform_fit": 0.10,
    }

    def __init__(self) -> None:
        self.vector_store = VectorStore()

    async def select(self, criteria: dict, top_n: int = 10) -> list[dict]:
        historical = await self.vector_store.search(
            "hot_products",
            query=criteria.get("keyword", ""),
            limit=50,
        )
        realtime = criteria.get("realtime_products", [])
        candidates = self._merge_candidates(historical, realtime)
        scored = []
        for product in candidates:
            score = self._calculate_score(product, criteria)
            scored.append({**product, "score": score})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_n]

    def _merge_candidates(self, historical: list, realtime: list) -> list[dict]:
        out: dict[str, dict] = {}
        for h in historical:
            payload = getattr(h, "payload", None) or h.get("payload", h)
            name = str(payload.get("name") or payload.get("title") or "")
            if name:
                out[name] = payload
        for p in realtime:
            name = str(p.get("name") or "")
            if name:
                out[name] = {**out.get(name, {}), **p}
        return list(out.values())

    def _calculate_score(self, product: dict, criteria: dict) -> float:
        scores = {
            "trend_score": self._trend_score(product),
            "competition": 1 - self._competition_score(product),
            "profit_margin": self._profit_score(product, criteria),
            "seasonality": self._season_score(product),
            "platform_fit": self._platform_fit_score(product, criteria),
        }
        return sum(self.WEIGHTS[k] * v for k, v in scores.items())

    @staticmethod
    def _trend_score(product: dict) -> float:
        sales = product.get("sales") or product.get("sales_count") or 0
        try:
            return min(1.0, float(str(sales).replace(",", "")) / 10000)
        except (ValueError, TypeError):
            return 0.5

    @staticmethod
    def _competition_score(product: dict) -> float:
        return 0.5

    @staticmethod
    def _profit_score(product: dict, criteria: dict) -> float:
        price = float(product.get("price") or 0)
        cost = float(product.get("cost_price") or criteria.get("cost_price") or price * 0.4)
        if price <= 0:
            return 0.3
        margin = (price - cost) / price
        return max(0.0, min(1.0, margin))

    @staticmethod
    def _season_score(product: dict) -> float:
        return 0.7

    @staticmethod
    def _platform_fit_score(product: dict, criteria: dict) -> float:
        target = criteria.get("platform", "douyin")
        return 1.0 if product.get("platform", target) == target else 0.6
