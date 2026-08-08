"""定价策略。"""
from __future__ import annotations

import numpy as np


class PricingModel:
    def calculate(self, product: dict, competitors: list[dict]) -> dict:
        cost = float(product.get("cost_price") or product.get("price", 0) * 0.4 or 0)
        comp_prices = [float(c["price"]) for c in competitors if c.get("price")]

        if not comp_prices:
            recommended = cost * 2.5 if cost > 0 else 99.0
            strategy = "cost_plus"
        else:
            median_price = float(np.median(comp_prices))
            recommended = median_price * 0.92
            strategy = "competitive"

        margin = (recommended - cost) / recommended if recommended > 0 else 0

        return {
            "recommended_price": round(recommended, 2),
            "cost_price": cost,
            "margin": round(margin, 4),
            "strategy": strategy,
            "competitor_median": round(float(np.median(comp_prices)), 2) if comp_prices else None,
        }
