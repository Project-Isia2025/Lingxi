"""投流 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import bootstrap

bootstrap.ensure_paths()

router = APIRouter(tags=["ad"])


class AdDeployPayload(BaseModel):
    keyword: str = Field(default="", max_length=80)
    platform: str = Field(default="douyin")
    daily_budget_cny: float = Field(default=100.0, ge=1)
    run_id: str = Field(default="")


@router.get("/api/ad/status")
def ad_api_status():
    from services.ad_traffic.client import ad_api_enabled

    return {"ok": True, "api_configured": ad_api_enabled()}


@router.post("/api/ad/deploy")
def deploy_ad(body: AdDeployPayload):
    from services.ad_optimizer import build_ad_plan, deploy_ad_plan

    plan = build_ad_plan(
        keyword=body.keyword or "campaign",
        platform=body.platform,
        strategy={},
        perception={},
        budget_limit=body.daily_budget_cny,
    )
    result = deploy_ad_plan(plan, run_id=body.run_id, sync_api=True)
    if not result.get("deployed") and not result.get("dry_run"):
        raise HTTPException(status_code=502, detail=result)
    return {"ok": True, **result}


@router.post("/api/ad/report/sync")
def sync_ad_report(run_id: str = Query(..., min_length=1), days: int = Query(7, ge=1, le=30)):
    from services.ad_feedback import sync_ad_report_for_run

    result = sync_ad_report_for_run(run_id, days=days)
    if not result.get("ok"):
        raise HTTPException(status_code=404 if result.get("error") == "no_campaign_for_run" else 502, detail=result)
    return result


@router.get("/api/ad/report/{run_id}")
def get_ad_report(run_id: str):
    from core.storage import get_ad_campaign_by_run

    campaign = get_ad_campaign_by_run(run_id)
    if not campaign:
        raise HTTPException(status_code=404, detail={"error": "no_campaign_for_run", "run_id": run_id})
    return {"ok": True, "campaign": campaign}


@router.get("/api/ad/campaigns")
def list_campaigns(limit: int = Query(20, ge=1, le=100)):
    from core.storage import list_ad_campaigns

    return {"ok": True, "items": list_ad_campaigns(limit=limit)}


@router.get("/api/ad/poll/status")
def ad_poll_status():
    from services.ad_scheduler import get_poll_status

    return get_poll_status()


@router.post("/api/ad/poll/run")
def ad_poll_run(sync: bool = Query(False, description="true=同步等待完成")):
    from services.ad_scheduler import poll_all_campaigns, trigger_poll_async

    if sync:
        return poll_all_campaigns()
    return trigger_poll_async()


@router.post("/api/ad/poll/start")
def ad_poll_start():
    from services.ad_scheduler import start_background_poller

    started = start_background_poller()
    return {"ok": started, "message": "background poller started" if started else "AD_POLL_ENABLED=0"}


@router.post("/api/ad/bid/evaluate")
def ad_bid_evaluate(run_id: str = Query(..., min_length=1), apply: bool = Query(False)):
    from services.ad_bid_engine import run_auto_bid_for_run

    result = run_auto_bid_for_run(run_id, apply=apply)
    if not result.get("ok"):
        raise HTTPException(status_code=404 if result.get("error") == "no_campaign_for_run" else 400, detail=result)
    return result


@router.post("/api/ad/bid/run_all")
def ad_bid_run_all(apply: bool = Query(True), limit: int = Query(50, ge=1, le=100)):
    from services.ad_bid_engine import run_auto_bid_all

    return run_auto_bid_all(limit=limit, apply=apply)


@router.post("/api/ad/bid/combined")
def ad_bid_combined(run_id: str = Query(..., min_length=1), apply: bool = Query(True)):
    from services.combined_roi_bid import run_combined_roi_bid_for_run

    result = run_combined_roi_bid_for_run(run_id, apply=apply)
    if not result.get("ok"):
        raise HTTPException(status_code=404 if "no_campaign" in str(result.get("error")) else 400, detail=result)
    return result
