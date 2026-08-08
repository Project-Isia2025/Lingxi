"""📊 数据感知 Agent（独立实现）。"""
from __future__ import annotations

from orchestrator.base import AgentResult, BaseAgent
from orchestrator.context import WorkflowContext
from services.perception import perceive_market


class DataPerceptionAgent(BaseAgent):
    name = "data_perception"
    phase = "perception"

    def run(self, ctx: WorkflowContext) -> AgentResult:
        goal = ctx.goal
        keyword = (goal.keyword or goal.title or goal.industry or "").strip()
        platform = (goal.platform or "douyin").strip().lower()

        if not keyword and not goal.reference_urls:
            return AgentResult(
                ok=False,
                agent=self.name,
                phase=self.phase,
                message="缺少 keyword 或 reference_urls",
            )

        out = perceive_market(
            keyword=keyword,
            platform=platform,
            reference_urls=list(goal.reference_urls or []),
            min_likes=goal.min_likes,
            min_followers=goal.min_followers,
            min_like_rate=goal.min_like_rate or None,
            limit=goal.discover_limit,
            include_hotlist=True,
        )
        ctx.perception = out
        n_comp = len(out.get("competitors") or [])
        n_bd = len(out.get("breakdowns") or [])
        trend = (out.get("traffic_trend") or {}).get("trend")
        vol = (out.get("traffic_volatility") or {}).get("level")
        ctx.log(self.name, self.phase, "ok", f"竞品 {n_comp}，拆解 {n_bd}，趋势 {trend}，波动 {vol}")

        return AgentResult(
            ok=True,
            agent=self.name,
            phase=self.phase,
            data=out,
            message=f"感知完成：{n_comp} 条竞品，{len(out.get('viral_rank') or [])} 条爆款排名",
            roi_delta=min(0.35, 0.05 + n_comp * 0.02 + n_bd * 0.03),
        )
