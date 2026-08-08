"""👑 总控大脑（Plan → Observe → Replan 循环）。"""
from __future__ import annotations

import threading
from typing import Any

import bootstrap
from core.storage import metrics_record
from orchestrator.base import AgentResult, BaseAgent
from orchestrator.content_agent import ContentAgent
from orchestrator.context import WorkflowContext, WorkflowGoal
from orchestrator.data_perception_agent import DataPerceptionAgent
from orchestrator.execution_agent import ExecutionAgent
from orchestrator.memory_agent import MemoryAgent
from orchestrator.replan import observe, replan, should_stop
from orchestrator.strategy_agent import StrategyAgent
from orchestrator.workflow_store import save_run
from services.knowledge import ingest_content_feedback, save_agent_episode
from services.roi import compute_roi

_ACTIVE: dict[str, threading.Thread] = {}
_CANCEL: set[str] = set()

_AGENT_PHASES = ("perception", "memory", "strategy", "content", "execution")
_RERUN_MAP = {
    "data_perception": 0,
    "memory": 1,
    "strategy": 2,
    "content": 3,
    "execution": 4,
}


def _conflict_needs_human(conflict: dict[str, Any]) -> bool:
    from services.workflow_decisions import human_decision_types

    return str(conflict.get("type") or "") in human_decision_types()


def _resolve_conflict(ctx: WorkflowContext, conflict: dict[str, Any]) -> dict[str, Any]:
    ctype = str(conflict.get("type") or "")
    resolution: dict[str, Any] = {"type": ctype, "action": "noted"}
    if ctype == "budget_over_limit":
        selected = conflict.get("selected")
        if selected and ctx.strategy:
            ctx.strategy["selected_provider"] = selected
            cost = ctx.strategy.get("video_cost_plan") or {}
            if isinstance(cost, dict):
                cost["selected_provider"] = selected
                cost["arbitrated"] = True
                ctx.strategy["video_cost_plan"] = cost
            resolution["action"] = "downgrade_provider"
    if ctype == "content_risk":
        resolution["action"] = "auto_replace_and_review"
        if ctx.content:
            ctx.content["needs_human_review"] = True
    if ctype == "content_duplicate":
        resolution["action"] = "warn_and_continue"
        if ctx.content:
            ctx.content["needs_rewrite"] = True
    if ctype == "quality_gate_failed":
        resolution["action"] = "block_publish"
    return resolution


def _post_run_feedback(ctx: WorkflowContext) -> None:
    script = str((ctx.content or {}).get("script") or "")
    keyword = str((ctx.strategy or {}).get("primary_keyword") or ctx.goal.keyword or "")
    platform = str((ctx.strategy or {}).get("target_platform") or ctx.goal.platform or "douyin")
    published = bool((ctx.execution or {}).get("published"))
    if script:
        ingest_content_feedback(
            run_id=ctx.run_id,
            script=script,
            keyword=keyword,
            platform=platform,
            published=published,
        )
    save_agent_episode(
        run_id=ctx.run_id,
        agent="orchestrator",
        observation=f"ROI={ctx.roi_score}",
        action="workflow_completed",
        payload={"status": ctx.status, "conflicts": len(ctx.conflicts)},
    )
    if (ctx.execution or {}).get("ad_deploy") and not (ctx.execution or {}).get("ad_report"):
        try:
            from services.ad_feedback import sync_ad_report_for_run

            report = sync_ad_report_for_run(ctx.run_id)
            if report.get("ok"):
                ctx.execution["ad_report"] = report
        except Exception:
            pass
    try:
        from services.combined_roi import apply_combined_roi_for_run, resolve_run_roi_inputs

        combined = apply_combined_roi_for_run(ctx.run_id, keyword=keyword)
        pub, ad = resolve_run_roi_inputs(ctx.run_id)
        score = float((combined or {}).get("combined_roi_score") or 0) if combined.get("ok") else None
        try:
            from services.roi_alert import dispatch_roi_alerts

            dispatch_roi_alerts(
                run_id=ctx.run_id,
                combined_roi=score,
                publish_roi=pub,
                ad_roi=ad,
                event="workflow_completed",
                extra={"keyword": keyword, "status": ctx.status},
            )
        except Exception:
            pass
    except Exception:
        pass


def _min_rerun_index(rerun_agents: list[str]) -> int:
    indices = [_RERUN_MAP[a] for a in rerun_agents if a in _RERUN_MAP]
    return min(indices) if indices else len(_AGENT_PHASES)


class OrchestratorAgent(BaseAgent):
    name = "orchestrator"
    phase = "orchestrate"

    def __init__(self) -> None:
        bootstrap.ensure_paths()
        self._agents: list[BaseAgent] = [
            DataPerceptionAgent(),
            MemoryAgent(),
            StrategyAgent(),
            ContentAgent(),
            ExecutionAgent(),
        ]

    def _run_agents(self, ctx: WorkflowContext, *, start: int = 0) -> tuple[bool, list[dict[str, Any]]]:
        all_conflicts: list[dict[str, Any]] = []
        for agent in self._agents[start:]:
            if ctx.run_id in _CANCEL:
                ctx.status = "cancelled"
                self._persist(ctx)
                return False, all_conflicts

            ctx.stage = agent.phase
            self._persist(ctx)
            try:
                result = agent.run(ctx)
            except Exception as exc:
                ctx.status = "failed"
                ctx.error = str(exc)
                ctx.log(agent.name, agent.phase, "failed", str(exc))
                self._persist(ctx)
                return False, all_conflicts

            if result.conflicts:
                human_conflicts = [c for c in result.conflicts if _conflict_needs_human(c)]
                if human_conflicts:
                    keyword = (ctx.goal.keyword or ctx.goal.title or "").strip()
                    from services.workflow_decisions import create_from_conflict

                    for c in human_conflicts:
                        create_from_conflict(run_id=ctx.run_id, conflict=c, goal_keyword=keyword)
                        c["resolution"] = {"action": "pending_human"}
                    all_conflicts.extend(result.conflicts)
                    ctx.conflicts.extend(result.conflicts)
                    ctx.status = "awaiting_decision"
                    ctx.stage = "awaiting_decision"
                    ctx.plan["resume_from"] = _RERUN_MAP.get(agent.name, 3) + 1
                    if agent.phase == "strategy":
                        ctx.plan["resume_from"] = 3
                    ctx.log(
                        self.name,
                        "awaiting_decision",
                        "waiting",
                        f"等待人工确认：{human_conflicts[0].get('type')}",
                    )
                    self._persist(ctx)
                    return False, all_conflicts
                for c in result.conflicts:
                    c["resolution"] = _resolve_conflict(ctx, c)
                all_conflicts.extend(result.conflicts)
                ctx.conflicts.extend(result.conflicts)

            if not result.ok and agent.phase in ("perception", "content"):
                ctx.status = "failed"
                ctx.error = result.message or f"{agent.name} 失败"
                self._persist(ctx)
                return False, all_conflicts
        return True, all_conflicts

    def run(self, ctx: WorkflowContext) -> AgentResult:
        ctx.stage = "planning"
        ctx.status = "running"
        ctx.plan = self._build_plan(ctx)
        ctx.plan["iteration"] = 1
        ctx.plan.setdefault("replan_history", [])
        self._persist(ctx)
        ctx.log(self.name, "plan", "ok", "目标已拆解为 5 个子任务")

        all_conflicts: list[dict[str, Any]] = []
        ok, conflicts = self._run_agents(ctx, start=0)
        all_conflicts.extend(conflicts)
        if not ok:
            if ctx.status == "awaiting_decision":
                return AgentResult(
                    ok=True,
                    agent=self.name,
                    phase=self.phase,
                    message="AI 已完成策略分析，等待您确认预算/出价后继续",
                    conflicts=all_conflicts,
                )
            return AgentResult(
                ok=False,
                agent=self.name,
                phase=self.phase,
                message=ctx.error or "工作流失败",
                conflicts=all_conflicts,
            )

        while getattr(ctx.goal, "enable_replan", False):
            ctx.stage = "observe"
            observation = observe(ctx)
            ctx.plan["last_observation"] = observation
            ctx.log(self.name, "observe", "ok", f"观察分 {observation.get('observation_score')}", **observation)
            self._persist(ctx)

            if should_stop(ctx, observation):
                break

            ctx.stage = "replan"
            replan_result = replan(ctx, observation)
            ctx.plan.setdefault("replan_history", []).append(replan_result)
            ctx.log(self.name, "replan", "ok", "；".join(replan_result.get("actions") or ["重规划"]))
            self._persist(ctx)

            if not replan_result.get("should_continue"):
                break

            start = _min_rerun_index(replan_result.get("rerun_agents") or [])
            if start >= len(self._agents):
                break
            ok, conflicts = self._run_agents(ctx, start=start)
            all_conflicts.extend(conflicts)
            if not ok:
                if ctx.status == "awaiting_decision":
                    return AgentResult(
                        ok=True,
                        agent=self.name,
                        phase=self.phase,
                        message="等待人工决策",
                        conflicts=all_conflicts,
                    )
                return AgentResult(
                    ok=False,
                    agent=self.name,
                    phase=self.phase,
                    message=ctx.error or "重规划后失败",
                    conflicts=all_conflicts,
                )

        return self._finalize(ctx, all_conflicts)

    def _finalize(self, ctx: WorkflowContext, all_conflicts: list[dict[str, Any]]) -> AgentResult:
        roi_result = compute_roi(ctx)
        ctx.roi_score = float(roi_result.get("roi_score") or 0)
        ctx.plan["roi_breakdown"] = roi_result.get("breakdown")
        ctx.plan["roi_grade"] = roi_result.get("grade")
        ctx.plan["recommendation"] = roi_result.get("recommendation")

        metrics_record(run_id=ctx.run_id, event_type="workflow_completed", value=ctx.roi_score)
        _post_run_feedback(ctx)

        ctx.stage = "done"
        ctx.status = "completed"
        self._persist(ctx)
        return AgentResult(
            ok=True,
            agent=self.name,
            phase=self.phase,
            data={
                "roi_score": ctx.roi_score,
                "roi_grade": roi_result.get("grade"),
                "conflicts": ctx.conflicts,
                "iterations": ctx.plan.get("iteration", 1),
            },
            message=roi_result.get("recommendation") or "工作流执行完成",
            conflicts=all_conflicts,
        )

    def continue_workflow(self, ctx: WorkflowContext, *, start: int = 0) -> AgentResult:
        """从指定 Agent 阶段继续执行（人工决策批准后）。"""
        ctx.status = "running"
        all_conflicts: list[dict[str, Any]] = list(ctx.conflicts or [])
        ok, conflicts = self._run_agents(ctx, start=start)
        all_conflicts.extend(conflicts)
        if not ok:
            if ctx.status == "awaiting_decision":
                return AgentResult(
                    ok=True,
                    agent=self.name,
                    phase=self.phase,
                    message="等待人工决策",
                    conflicts=all_conflicts,
                )
            return AgentResult(
                ok=False,
                agent=self.name,
                phase=self.phase,
                message=ctx.error or "工作流失败",
                conflicts=all_conflicts,
            )

        while getattr(ctx.goal, "enable_replan", False):
            ctx.stage = "observe"
            observation = observe(ctx)
            ctx.plan["last_observation"] = observation
            ctx.log(self.name, "observe", "ok", f"观察分 {observation.get('observation_score')}", **observation)
            self._persist(ctx)
            if should_stop(ctx, observation):
                break
            ctx.stage = "replan"
            replan_result = replan(ctx, observation)
            ctx.plan.setdefault("replan_history", []).append(replan_result)
            ctx.log(self.name, "replan", "ok", "；".join(replan_result.get("actions") or ["重规划"]))
            self._persist(ctx)
            if not replan_result.get("should_continue"):
                break
            next_start = _min_rerun_index(replan_result.get("rerun_agents") or [])
            if next_start >= len(self._agents):
                break
            ok, conflicts = self._run_agents(ctx, start=next_start)
            all_conflicts.extend(conflicts)
            if not ok:
                if ctx.status == "awaiting_decision":
                    return AgentResult(
                        ok=True,
                        agent=self.name,
                        phase=self.phase,
                        message="等待人工决策",
                        conflicts=all_conflicts,
                    )
                return AgentResult(
                    ok=False,
                    agent=self.name,
                    phase=self.phase,
                    message=ctx.error or "重规划后失败",
                    conflicts=all_conflicts,
                )

        return self._finalize(ctx, all_conflicts)

    def _build_plan(self, ctx: WorkflowContext) -> dict[str, Any]:
        keyword = (ctx.goal.keyword or ctx.goal.title or "").strip()
        assignments = [
            {
                "order": 1,
                "agent": "data_perception",
                "task": "竞品/热点/流量波动感知",
                "outputs": ["competitors", "viral_rank", "traffic_volatility"],
            },
            {
                "order": 2,
                "agent": "memory",
                "task": "知识库/SOP/违禁词召回",
                "outputs": ["material_context", "sop_entries", "forbidden_rows"],
            },
            {
                "order": 3,
                "agent": "strategy",
                "task": "选品定价与投流出价决策",
                "outputs": ["product_selection", "pricing_tiers", "ad_plan"],
            },
            {
                "order": 4,
                "agent": "content",
                "task": "脚本生成/混剪计划/去重风控",
                "outputs": ["script", "mix_plan", "variants"],
            },
            {
                "order": 5,
                "agent": "execution",
                "task": "质检/ffmpeg混剪/发布/投流API",
                "outputs": ["publish_plan", "ad_optimize_plan", "mix_render", "quality_gate"],
            },
        ]
        return {
            "goal": ctx.goal.title or keyword or "营销 campaign",
            "keyword": keyword,
            "platform": ctx.goal.platform,
            "success_metrics": ["roi_score", "publish_ok", "script_unique"],
            "enable_replan": bool(getattr(ctx.goal, "enable_replan", False)),
            "max_iterations": int(getattr(ctx.goal, "max_iterations", 1) or 1),
            "assignments": assignments,
            "steps": [{"order": a["order"], "agent": a["agent"], "task": a["task"]} for a in assignments],
        }

    def _persist(self, ctx: WorkflowContext) -> None:
        try:
            save_run(ctx.to_dict())
        except Exception:
            pass


def run_workflow(goal: WorkflowGoal, *, async_mode: bool = False) -> WorkflowContext:
    bootstrap.ensure_paths()
    ctx = WorkflowContext(goal=goal)
    orch = OrchestratorAgent()

    if async_mode:
        def _worker() -> None:
            try:
                orch.run(ctx)
            finally:
                _ACTIVE.pop(ctx.run_id, None)

        t = threading.Thread(target=_worker, daemon=True, name=f"orch-{ctx.run_id[:8]}")
        _ACTIVE[ctx.run_id] = t
        t.start()
        save_run(ctx.to_dict())
        return ctx

    orch.run(ctx)
    return ctx


def cancel_workflow(run_id: str) -> bool:
    rid = str(run_id or "").strip()
    if not rid:
        return False
    _CANCEL.add(rid)
    return True


def resume_workflow(run_id: str) -> dict[str, Any]:
    """人工批准决策后，从暂停点继续 Agent 工作流。"""
    from orchestrator.context import WorkflowContext
    from orchestrator.workflow_store import load_run

    data = load_run(run_id)
    if not data:
        return {"ok": False, "error": "run_not_found"}
    if str(data.get("status") or "") not in ("running", "awaiting_decision"):
        return {"ok": False, "error": "run_not_resumable", "status": data.get("status")}

    ctx = WorkflowContext.from_dict(data)
    start = int((ctx.plan or {}).get("resume_from") or 3)
    orch = OrchestratorAgent()

    if run_id in _ACTIVE:
        return {"ok": False, "error": "run_already_active"}

    def _worker() -> None:
        try:
            orch.continue_workflow(ctx, start=start)
        finally:
            _ACTIVE.pop(run_id, None)

    t = threading.Thread(target=_worker, daemon=True, name=f"orch-resume-{run_id[:8]}")
    _ACTIVE[run_id] = t
    t.start()
    save_run(ctx.to_dict())
    return {"ok": True, "run_id": run_id, "resume_from": start, "status": "running"}
