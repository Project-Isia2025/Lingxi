"""六 Agent 工作流 API（独立项目）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import bootstrap

bootstrap.ensure_paths()

router = APIRouter(tags=["orchestrator"])


class OrchestratorRunPayload(BaseModel):
    title: str = Field(default="", max_length=120)
    keyword: str = Field(default="", max_length=80)
    platform: str = Field(default="douyin")
    industry: str = Field(default="", max_length=80)
    org_id: str = Field(default="")
    budget_limit: float = Field(default=0.0, ge=0)
    auto_execute: bool = Field(default=False, description="任务入队")
    auto_publish: bool = Field(default=False, description="自动发布到创作者中心（需 video_path）")
    auto_matrix_publish: bool = Field(default=False, description="联合 ROI 策略矩阵入队（需 video_path）")
    video_path: str = Field(default="", description="本地成片路径，auto_publish 必填")
    reference_urls: list[str] = Field(default_factory=list, max_length=5)
    min_likes: int = Field(default=0, ge=0)
    min_followers: int = Field(default=0, ge=0)
    discover_limit: int = Field(default=15, ge=1, le=30)
    video_provider: str = Field(default="")
    enable_replan: bool = Field(default=False, description="启用 Plan→Observe→Replan 循环")
    max_iterations: int = Field(default=2, ge=1, le=5)
    async_mode: bool = Field(default=True)


class LangGraphRunPayload(BaseModel):
    goal: str = Field(default="推广商品", max_length=200)
    platform: str = Field(default="douyin")
    budget: float = Field(default=1000.0, ge=0)
    max_iterations: int = Field(default=1, ge=1, le=10)
    materials: list[str] = Field(default_factory=list)
    async_mode: bool = Field(default=False)


@router.get("/api/orchestrator/routing")
def orchestrator_routing():
    from orchestrator.routing import orchestrator_routing_info

    return orchestrator_routing_info()


@router.get("/api/orchestrator/langgraph/info")
def langgraph_info():
    from orchestrator.graph import Orchestrator
    from orchestrator.routing import orchestrator_routing_info

    return {"ok": True, **Orchestrator().graph_info(), "routing": orchestrator_routing_info()}


@router.post("/api/orchestrator/langgraph/run")
async def langgraph_run(body: LangGraphRunPayload):
    """LangGraph 总控大脑（实验路径）— 生产请用 POST /api/orchestrator/run。"""
    from orchestrator.routing import langgraph_enabled, orchestrator_routing_info

    if not langgraph_enabled():
        raise HTTPException(
            status_code=403,
            detail={
                "ok": False,
                "error": "langgraph_disabled",
                "hint": "设置 LANGGRAPH_ORCHESTRATOR_ENABLED=1 启用实验路径",
                "routing": orchestrator_routing_info(),
            },
        )
    from orchestrator.graph import Orchestrator
    from orchestrator.state import build_initial_state

    state = build_initial_state(
        goal=body.goal,
        platform=body.platform,
        total_budget=body.budget,
        max_iterations=body.max_iterations,
        materials=body.materials,
    )

    if body.async_mode:
        import asyncio

        orch = Orchestrator()
        task = asyncio.create_task(orch.graph.ainvoke(state))
        return {"ok": True, "status": "started", "run_id": state["run_id"], "task": str(task)}

    orch = Orchestrator()
    final = await orch.graph.ainvoke(state)
    return {
        "ok": True,
        "run_id": final.get("run_id"),
        "status": final.get("status"),
        "current_roi": final.get("current_roi"),
        "iteration": final.get("iteration"),
        "result": final,
    }


@router.get("/api/orchestrator/status")
def orchestrator_status():
    from orchestrator.orchestrator_agent import _ACTIVE

    return {
        "ok": True,
        "project": "五层AI智能体矩阵",
        "active_runs": len(_ACTIVE),
        "agents": [
            {"id": "orchestrator", "role": "总控大脑"},
            {"id": "data_perception", "role": "数据感知"},
            {"id": "memory", "role": "记忆与知识库"},
            {"id": "strategy", "role": "策略"},
            {"id": "content", "role": "内容"},
            {"id": "execution", "role": "执行"},
        ],
    }


@router.post("/api/orchestrator/run")
def start_orchestrator_run(body: OrchestratorRunPayload):
    keyword = body.keyword.strip()
    if not keyword and not body.reference_urls:
        raise HTTPException(status_code=400, detail="请提供 keyword 或 reference_urls")

    from orchestrator.context import WorkflowGoal
    from orchestrator.orchestrator_agent import run_workflow

    goal = WorkflowGoal(
        title=body.title.strip(),
        keyword=keyword,
        platform=body.platform.strip().lower() or "douyin",
        industry=body.industry.strip(),
        org_id=body.org_id.strip(),
        budget_limit=float(body.budget_limit or 0),
        auto_execute=bool(body.auto_execute),
        auto_publish=bool(body.auto_publish),
        auto_matrix_publish=bool(body.auto_matrix_publish),
        video_path=body.video_path.strip(),
        reference_urls=[str(u).strip() for u in body.reference_urls if str(u).strip()],
        min_likes=body.min_likes,
        min_followers=body.min_followers,
        discover_limit=body.discover_limit,
        video_provider=body.video_provider.strip(),
        enable_replan=bool(body.enable_replan),
        max_iterations=body.max_iterations,
    )
    ctx = run_workflow(goal, async_mode=bool(body.async_mode))
    out = ctx.to_dict()
    out["ok"] = True
    return out


@router.get("/api/orchestrator/runs")
def list_orchestrator_runs(limit: int = 30, org_id: str = ""):
    from orchestrator.workflow_store import list_runs

    return {"ok": True, "runs": list_runs(org_id=org_id, limit=limit)}


@router.get("/api/orchestrator/runs/{run_id}")
def get_orchestrator_run(run_id: str):
    from orchestrator.workflow_store import load_run

    data = load_run(run_id)
    if not data:
        raise HTTPException(status_code=404, detail="工作流不存在")
    data["ok"] = True
    return data


@router.post("/api/orchestrator/runs/{run_id}/cancel")
def cancel_orchestrator_run(run_id: str):
    from orchestrator.orchestrator_agent import cancel_workflow
    from orchestrator.workflow_store import load_run, save_run

    data = load_run(run_id)
    if not data:
        raise HTTPException(status_code=404, detail="工作流不存在")
    cancel_workflow(run_id)
    data["status"] = "cancelled"
    save_run(data)
    return {"ok": True, "run_id": run_id, "status": "cancelled"}
