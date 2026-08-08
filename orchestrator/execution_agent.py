"""🚀 执行 Agent（独立实现）。"""
from __future__ import annotations

from orchestrator.base import AgentResult, BaseAgent
from orchestrator.context import WorkflowContext
from services.execution import build_execution


def _pick_url(ctx: WorkflowContext) -> str:
    for u in ctx.goal.reference_urls or []:
        if str(u).startswith("http"):
            return str(u).strip()
    for item in (ctx.perception.get("competitors") or []):
        url = str(item.get("url") or "").strip()
        if url.startswith("http"):
            return url
    return ""


class ExecutionAgent(BaseAgent):
    name = "execution"
    phase = "execution"

    def run(self, ctx: WorkflowContext) -> AgentResult:
        exec_url = _pick_url(ctx)
        execution_out = build_execution(
            run_id=ctx.run_id,
            goal=ctx.goal,
            strategy=ctx.strategy or {},
            content=ctx.content or {},
            exec_url=exec_url,
        )
        ctx.execution = execution_out
        qg = execution_out.get("quality_gate") or {}
        review = execution_out.get("review") or {}
        if review.get("ok") and review.get("status") == "pending_review":
            ctx.status = "awaiting_review"
            ctx.log(
                self.name,
                self.phase,
                "waiting",
                "成片已生成，等待人工确认后 AI 将继续发布",
            )
        if not qg.get("passed") and ctx.goal.auto_publish:
            return AgentResult(
                ok=bool(execution_out.get("ready")),
                agent=self.name,
                phase=self.phase,
                data=execution_out,
                message="质检未通过，已阻止自动发布",
                roi_delta=0.05,
                conflicts=[{"type": "quality_gate_failed", "checks": qg.get("warnings")}],
            )
        ctx.log(
            self.name,
            self.phase,
            "ok" if execution_out.get("ready") else "degraded",
            "执行完成"
            + ("，已发布" if execution_out.get("published") else "")
            + ("，任务已入队" if execution_out.get("auto_started") and not execution_out.get("published") else ""),
        )
        return AgentResult(
            ok=bool(execution_out.get("ready")),
            agent=self.name,
            phase=self.phase,
            data=execution_out,
            message="发布完成" if execution_out.get("published") else "执行计划就绪",
            roi_delta=0.25 if execution_out.get("published") else (0.15 if execution_out.get("auto_started") else 0.08),
        )
