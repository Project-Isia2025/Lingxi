"""ROI 监控器 — 汇总投放消耗与收入。"""
from __future__ import annotations

from typing import Any

from orchestrator.state import GlobalState


class ROIMonitor:
    """ROI 监控 — 支持模拟增量与 execution 结果回写。"""

    async def update(self, state: GlobalState) -> dict[str, Any]:
        spend = float(state.get("total_spend") or 0)
        revenue = float(state.get("total_revenue") or 0)

        exec_data = state.get("execution_data") or {}
        pub = exec_data.get("publish_result") or {}
        success = sum(1 for v in pub.values() if isinstance(v, dict) and v.get("status") == "success")

        # 模拟本轮回采（指南 Phase 6 示例逻辑）
        spend += 50.0 + success * 10
        revenue += 120.0 + success * 80

        # 若 execution 含 ad 数据则优先使用
        ad = exec_data.get("ad_campaign") or {}
        if ad.get("spend") is not None:
            spend = float(ad["spend"])
        if ad.get("revenue") is not None:
            revenue = float(ad["revenue"])

        roi = revenue / spend if spend > 0 else 0.0
        grade = self._grade(roi)

        snapshot = {
            "total_spend": round(spend, 2),
            "total_revenue": round(revenue, 2),
            "current_roi": round(roi, 4),
            "roi_grade": grade,
            "iteration": state.get("iteration", 0),
        }

        try:
            from memory.knowledge_base import KnowledgeBase

            kb = KnowledgeBase()
            await kb.log_decision(
                agent_name="orchestrator",
                decision_type="monitor_roi",
                input_data={"run_id": state.get("run_id"), "iteration": state.get("iteration")},
                output_data=snapshot,
                confidence=min(1.0, roi / 2.0) if roi > 0 else 0.1,
            )
        except Exception:
            pass

        return snapshot

    def is_healthy(self, state: GlobalState) -> bool:
        return float(state.get("current_roi") or 0) >= 1.0

    def budget_exhausted(self, state: GlobalState) -> bool:
        spend = float(state.get("total_spend") or 0)
        budget = float(state.get("total_budget") or 0)
        return budget > 0 and spend >= budget

    def should_stop(self, state: GlobalState) -> tuple[bool, str]:
        if self.budget_exhausted(state):
            return True, "budget_exhausted"
        if int(state.get("iteration") or 0) >= int(state.get("max_iterations") or 10):
            return True, "max_iterations"
        if not self.is_healthy(state) and int(state.get("iteration") or 0) >= 1:
            return True, "roi_below_threshold"
        return False, ""

    @staticmethod
    def _grade(roi: float) -> str:
        if roi >= 2.0:
            return "A"
        if roi >= 1.0:
            return "B"
        if roi >= 0.5:
            return "C"
        return "D"
