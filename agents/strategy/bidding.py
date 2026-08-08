"""投放出价优化。"""
from __future__ import annotations

from scipy.optimize import minimize


class BiddingOptimizer:
    def __init__(self) -> None:
        self.history: list = []

    def optimize(self, budget: float, historical_data: list[dict]) -> dict:
        if not historical_data:
            return {"bid_cpc": 0.5, "expected_cpa": None, "strategy": "cold_start"}

        bids = [float(d["bid"]) for d in historical_data]
        conversions = [float(d["conversions"]) for d in historical_data]

        def neg_objective(bid_arr):
            bid = bid_arr[0]
            expected_conv = self._predict_conversions(bid, bids, conversions)
            expected_cost = bid * expected_conv
            if expected_cost > budget:
                return 1e6
            return -expected_conv

        result = minimize(neg_objective, x0=[0.5], bounds=[(0.1, 5.0)])
        optimal_bid = float(result.x[0])
        expected_conv = max(0.1, -float(result.fun))

        return {
            "bid_cpc": round(optimal_bid, 2),
            "expected_conversions": round(expected_conv, 1),
            "expected_cpa": round(budget / max(expected_conv, 1), 2),
            "strategy": "optimized",
        }

    def _predict_conversions(self, bid: float, hist_bids: list, hist_conv: list) -> float:
        if not hist_bids:
            return 0.0
        weights = [1 / (abs(b - bid) + 0.1) for b in hist_bids]
        total_w = sum(weights)
        return sum(w * c for w, c in zip(weights, hist_conv)) / total_w
