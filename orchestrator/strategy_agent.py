"""🧠 策略 Agent（独立实现）。"""
from __future__ import annotations

from orchestrator.base import AgentResult, BaseAgent
from orchestrator.context import WorkflowContext
from services.strategy import build_strategy


class StrategyAgent(BaseAgent):
    name = "strategy"
    phase = "strategy"

    def run(self, ctx: WorkflowContext) -> AgentResult:
        goal = ctx.goal
        keyword = (goal.keyword or goal.title or "").strip()
        platform = (goal.platform or "douyin").strip().lower()

        strategy_out = build_strategy(
            keyword=keyword,
            platform=platform,
            perception=ctx.perception or {},
            memory=ctx.memory or {},
            budget_limit=float(goal.budget_limit or 0),
            video_provider=goal.video_provider,
        )
        conflicts = list(strategy_out.pop("_conflicts", []) or [])
        ctx.strategy = strategy_out
        ctx.log(
            self.name,
            self.phase,
            "ok",
            f"{strategy_out.get('content_angle', '')[:40]} | 投流 {((strategy_out.get('ad_plan') or {}).get('phase'))}",
        )
        return AgentResult(
            ok=True,
            agent=self.name,
            phase=self.phase,
            data=strategy_out,
            message="策略规划完成",
            roi_delta=0.2,
            conflicts=conflicts,
        )
