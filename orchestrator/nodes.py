"""LangGraph 编排节点实现。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.content import ContentAgent
from agents.execution import ExecutionAgent
from agents.perception import PerceptionAgent
from agents.strategy import StrategyAgent
from orchestrator.roi_monitor import ROIMonitor
from orchestrator.state import GlobalState


class OrchestratorNodes:
    """总控大脑节点 — 调用四个子 Agent。"""

    def __init__(self) -> None:
        self.perception = PerceptionAgent()
        self.strategy = StrategyAgent()
        self.content = ContentAgent()
        self.execution = ExecutionAgent()
        self.roi_monitor = ROIMonitor()

    async def perceive(self, state: GlobalState) -> dict[str, Any]:
        keyword = state.get("goal", "")
        platform = state.get("platform", "douyin")
        try:
            result = await self.perception.execute(
                {
                    "type": "scrape_products",
                    "platform": platform,
                    "category": keyword,
                }
            )
            return {
                "perception_data": result,
                "iteration": state.get("iteration", 0) + 1,
                "status": "perceived",
            }
        except Exception as exc:
            errors = list(state.get("errors") or [])
            errors.append(f"perceive: {exc}")
            return {"errors": errors, "iteration": state.get("iteration", 0) + 1, "status": "error"}

    async def analyze_strategy(self, state: GlobalState) -> dict[str, Any]:
        try:
            result = await self.strategy.execute(
                {
                    "type": "full_strategy",
                    "criteria": {
                        "keyword": state.get("goal", ""),
                        "realtime_products": state.get("perception_data", {}).get("products", []),
                        "platform": state.get("platform", "douyin"),
                    },
                    "budget": state.get("total_budget", 1000),
                }
            )
            if result.get("error"):
                errors = list(state.get("errors") or [])
                errors.append(result["error"])
                return {"strategy_data": result, "errors": errors}
            return {"strategy_data": result, "status": "strategy_ready"}
        except Exception as exc:
            errors = list(state.get("errors") or [])
            errors.append(f"strategy: {exc}")
            return {"errors": errors, "status": "error"}

    async def create_content(self, state: GlobalState) -> dict[str, Any]:
        strategy = state.get("strategy_data") or {}
        product = strategy.get("product") or {"name": state.get("goal", "商品")}
        iteration = state.get("iteration", 0)
        run_id = state.get("run_id", "run")
        out_dir = Path("data/output/videos")
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / f"orch_{run_id[:8]}_{iteration}.mp4")

        try:
            result = await self.content.execute(
                {
                    "type": "produce_video",
                    "product": product,
                    "materials": state.get("materials", []),
                    "output_path": output_path,
                }
            )
            return {"content_data": result, "status": "content_ready"}
        except Exception as exc:
            errors = list(state.get("errors") or [])
            errors.append(f"content: {exc}")
            return {"errors": errors, "status": "error"}

    async def execute(self, state: GlobalState) -> dict[str, Any]:
        content = state.get("content_data") or {}
        platform = state.get("platform", "douyin")
        try:
            result = await self.execution.execute(
                {
                    "type": "publish",
                    "video_path": content.get("video_path", ""),
                    "metadata": {
                        "title": f"好物推荐 - {state.get('iteration', 0)}",
                        "tags": ["好物推荐", "带货"],
                    },
                    "platforms": [platform],
                }
            )
            return {"execution_data": result, "status": "executed"}
        except Exception as exc:
            errors = list(state.get("errors") or [])
            errors.append(f"execution: {exc}")
            return {"errors": errors, "status": "error"}

    async def monitor_roi(self, state: GlobalState) -> dict[str, Any]:
        snapshot = await self.roi_monitor.update(state)
        stop, reason = self.roi_monitor.should_stop({**state, **snapshot})
        status = "completed" if stop else "optimizing"
        return {**snapshot, "status": status, "stop_reason": reason if stop else ""}

    async def arbitrate(self, state: GlobalState) -> dict[str, Any]:
        """冲突仲裁 — 大额出价需审批；离线模式自动通过。"""
        strategy = state.get("strategy_data") or {}
        bidding = strategy.get("bid_cpc") or strategy.get("bidding") or {}
        bid = float(bidding.get("bid_cpc") or 0)
        pending = list(state.get("pending_approvals") or [])

        if bid > 2.0:
            pending.append(
                {
                    "type": "high_bid",
                    "bid_cpc": bid,
                    "resolution": "auto_approved",
                    "note": "离线模式自动通过，生产环境应接入人工审批",
                }
            )
        return {"pending_approvals": pending, "status": "arbitrated"}

    def needs_approval(self, state: GlobalState) -> bool:
        strategy = state.get("strategy_data") or {}
        bid = float((strategy.get("bidding") or {}).get("bid_cpc") or 0)
        return bid > 2.0

    def should_continue(self, state: GlobalState) -> bool:
        roi = float(state.get("current_roi") or 0)
        budget = float(state.get("total_budget") or 0)
        spend = float(state.get("total_spend") or 0)
        iteration = int(state.get("iteration") or 0)
        max_iter = int(state.get("max_iterations") or 10)

        if iteration >= max_iter:
            return False
        if budget > 0 and spend >= budget:
            return False
        # ROI > 1.0 且预算未耗尽 -> 继续循环优化
        if roi > 1.0 and spend < budget:
            return True
        return False
