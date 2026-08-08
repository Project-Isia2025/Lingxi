"""带货活动 API — 可在 9200 与 8000 复用。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.campaign_store import create, get, list_campaigns, update
from api.schemas import CampaignRequest, CampaignResponse, CampaignStatusResponse
from orchestrator.graph import Orchestrator
from orchestrator.state import build_initial_state

router = APIRouter(tags=["campaign"])


async def _run_campaign(campaign_id: str, initial_state: dict) -> None:
    orchestrator = Orchestrator()
    try:
        final = await orchestrator.graph.ainvoke(initial_state)
        update(campaign_id, status=final.get("status", "completed"), state=final)
    except Exception as exc:
        update(campaign_id, status="failed", error=str(exc))


@router.post("/campaigns/start", response_model=CampaignResponse)
async def start_campaign(req: CampaignRequest, bg: BackgroundTasks):
    """启动一个带货活动 — 后台异步执行 LangGraph 编排。"""
    campaign_id = str(uuid.uuid4())
    create(campaign_id, goal=req.goal, platform=req.platform, budget=req.budget)

    initial_state = build_initial_state(
        goal=req.goal,
        platform=req.platform,
        total_budget=req.budget,
        materials=req.materials,
        max_iterations=req.max_iterations,
        run_id=campaign_id,
    )

    if req.sync:
        await _run_campaign(campaign_id, initial_state)
        row = get(campaign_id) or {}
        if row.get("status") == "failed":
            raise HTTPException(status_code=500, detail=row.get("error") or "活动执行失败")
        return CampaignResponse(status=row.get("status", "completed"), campaign_id=campaign_id)

    bg.add_task(_run_campaign, campaign_id, initial_state)
    return CampaignResponse(status="started", campaign_id=campaign_id)


@router.get("/campaigns/{campaign_id}/status", response_model=CampaignStatusResponse)
async def get_campaign_status(campaign_id: str):
    """查询活动状态和 ROI。"""
    row = get(campaign_id)
    if row is None:
        raise HTTPException(status_code=404, detail="未找到该活动")
    state = row.get("state") or {}
    return CampaignStatusResponse(
        campaign_id=campaign_id,
        status=row.get("status", "unknown"),
        goal=row.get("goal"),
        platform=row.get("platform"),
        current_roi=state.get("current_roi"),
        total_spend=state.get("total_spend"),
        total_revenue=state.get("total_revenue"),
        iteration=state.get("iteration"),
        errors=state.get("errors"),
        stop_reason=state.get("stop_reason"),
    )


@router.get("/campaigns")
async def list_all_campaigns(limit: int = 20):
    rows = list_campaigns(limit=limit)
    platform_label = {"douyin": "抖音", "xiaohongshu": "小红书", "xhs": "小红书", "shipinhao": "视频号", "weixin": "视频号"}
    status_label = {
        "started": "正在准备",
        "running": "进行中",
        "completed": "已完成",
        "failed": "出错了",
    }
    items = []
    for row in rows:
        plat = str(row.get("platform") or "douyin")
        st = str(row.get("status") or "unknown")
        state = row.get("state") or {}
        items.append(
            {
                "campaign_id": row.get("campaign_id"),
                "goal": row.get("goal"),
                "platform": plat,
                "platform_label": platform_label.get(plat, plat),
                "status": st,
                "status_label": status_label.get(st, st),
                "budget": row.get("budget"),
                "current_roi": state.get("current_roi"),
                "updated_at": row.get("updated_at"),
            }
        )
    return {"ok": True, "campaigns": items}
