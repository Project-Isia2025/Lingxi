"""Agent 工作流 API — AI 自动调度，人类关键决策。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import bootstrap

bootstrap.ensure_paths()

router = APIRouter(tags=["workflow"])


class WorkflowStartRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=200, description="推广目标/关键词")
    platform: str = Field(default="douyin")
    budget: float = Field(default=3000.0, ge=0)
    enable_replan: bool = Field(default=True, description="AI 自动观察数据并重规划")
    max_iterations: int = Field(default=3, ge=1, le=5)


class DecisionRejectRequest(BaseModel):
    reason: str = Field(default="不同意该方案", min_length=2, max_length=500)


@router.get("/api/workflow/overview")
def workflow_overview(limit: int = 8):
    from services.workflow_cockpit import build_workflow_overview

    return build_workflow_overview(limit=limit)


@router.get("/api/workflow/runs/{run_id}")
def workflow_run_detail(run_id: str):
    from services.workflow_cockpit import build_run_detail

    detail = build_run_detail(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return detail


@router.post("/api/workflow/start")
def workflow_start(body: WorkflowStartRequest):
    """启动完整 Agent 工作流 — 五层编排 + 自动 Replan。"""
    from orchestrator.context import WorkflowGoal
    from orchestrator.orchestrator_agent import run_workflow

    goal_text = body.goal.strip()
    goal = WorkflowGoal(
        title=goal_text,
        keyword=goal_text,
        platform=body.platform.strip().lower() or "douyin",
        budget_limit=float(body.budget or 0),
        auto_execute=True,
        enable_replan=bool(body.enable_replan),
        max_iterations=body.max_iterations,
    )
    ctx = run_workflow(goal, async_mode=True)

    try:
        from services.publish_worker import start_background_worker

        start_background_worker()
    except Exception:
        pass

    return {
        "ok": True,
        "run_id": ctx.run_id,
        "status": ctx.status,
        "stage": ctx.stage,
        "message": "AI 工作流已启动：感知→决策→执行 全自动；仅在关键节点等您点头确认",
    }


@router.post("/api/workflow/runs/{run_id}/cancel")
def workflow_cancel(run_id: str):
    """应急兜底 — 人工终止卡住或不需要的任务。"""
    from orchestrator.orchestrator_agent import cancel_workflow
    from orchestrator.workflow_store import load_run, save_run

    data = load_run(run_id)
    if not data:
        raise HTTPException(status_code=404, detail="工作流不存在")
    cancel_workflow(run_id)
    data["status"] = "cancelled"
    data["stage"] = "done"
    data["error"] = "人工应急终止"
    save_run(data)
    return {"ok": True, "run_id": run_id, "message": "任务已终止（应急兜底）"}


@router.post("/api/workflow/decisions/{decision_id}/approve")
def workflow_decision_approve(decision_id: str, token: str = Query("")):
    if decision_id.startswith("dec-"):
        from services.workflow_decisions import resolve_decision

        result = resolve_decision(decision_id=decision_id, approved=True)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error") or "审批失败")
        return result

    from services.review_queue import approve_review

    result = approve_review(review_id=decision_id, token=token)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "审批失败")
    return {
        "ok": True,
        "message": "已确认，AI 将继续自动发布并优化",
        **result,
    }


@router.post("/api/workflow/decisions/{decision_id}/reject")
def workflow_decision_reject(decision_id: str, body: DecisionRejectRequest, token: str = Query("")):
    if decision_id.startswith("dec-"):
        from services.workflow_decisions import resolve_decision

        result = resolve_decision(decision_id=decision_id, approved=False, reason=body.reason.strip())
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error") or "打回失败")
        return result

    from services.review_queue import reject_review

    result = reject_review(review_id=decision_id, reason=body.reason.strip(), token=token)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "打回失败")
    return {
        "ok": True,
        "message": "已打回，AI 将学习反馈并在下一轮自动优化",
        **result,
    }


@router.delete("/api/workflow/runs/{run_id}")
def workflow_delete_run(run_id: str):
    """删除已完成/已取消/失败的历史工作流记录。"""
    from services.task_cleanup import delete_workflow_run

    result = delete_workflow_run(run_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return {"ok": True, "message": "历史任务已删除", **result}


@router.delete("/api/workflow/decisions/{decision_id}")
def workflow_delete_decision(decision_id: str):
    """移除待处理或已完成的决策/审核卡片（不触发业务逻辑）。"""
    if decision_id.startswith("dec-"):
        from services.task_cleanup import delete_workflow_decision

        result = delete_workflow_decision(decision_id)
    else:
        from services.review_queue import delete_review_item

        result = delete_review_item(decision_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return {"ok": True, "message": "已从列表移除", **result}


@router.post("/api/workflow/decisions/clear-pending")
def workflow_clear_pending_decisions():
    """一键清空全部待确认成片（测试数据 / 历史积压）。"""
    from services.task_cleanup import clear_all_pending_reviews

    result = clear_all_pending_reviews()
    return {"ok": True, "message": f"已清空 {result.get('deleted', 0)} 条待确认任务", **result}


@router.post("/api/workflow/runs/clear-completed")
def workflow_clear_completed_runs():
    """清空全部已完成 / 已取消 / 失败的工作流记录（Dashboard 一键清理）。"""
    from services.task_cleanup import clear_all_completed_runs

    result = clear_all_completed_runs()
    deleted = int(result.get("deleted") or 0)
    return {
        "ok": True,
        "message": f"已清空 {deleted} 条已完成任务",
        **result,
    }


@router.post("/api/workflow/cleanup")
def workflow_cleanup_completed(expired_only: bool = Query(True, description="true=仅清理超出保留期的记录")):
    """清理历史任务。Dashboard 请用 /api/workflow/runs/clear-completed。"""
    if expired_only:
        from services.task_cleanup import purge_all_completed_tasks

        result = purge_all_completed_tasks()
        total = int(result.get("deleted_total") or 0)
        result["message"] = f"已清理 {total} 条过期历史（保留期内记录不受影响）"
        return result

    from services.task_cleanup import clear_all_completed_runs

    result = clear_all_completed_runs()
    result["deleted_total"] = int(result.get("deleted") or 0)
    result["message"] = f"已清空 {result['deleted_total']} 条已完成任务"
    return result


@router.get("/api/workflow/cleanup/status")
def workflow_cleanup_status():
    from services.task_cleanup import cleanup_status

    return cleanup_status()
