"""发布后监控 API。"""
from __future__ import annotations

from fastapi import APIRouter, Query

import bootstrap

bootstrap.ensure_paths()

router = APIRouter(tags=["monitor"])


@router.get("/api/monitor/post-publish/status")
def post_publish_monitor_status():
    from services.post_publish_monitor_worker import get_status

    return get_status()


@router.post("/api/monitor/post-publish/poll")
def post_publish_monitor_poll(limit: int = Query(5, ge=1, le=20)):
    from services.post_publish_monitor import poll_due_monitors

    return poll_due_monitors(limit=limit)


@router.post("/api/monitor/post-publish/start")
def post_publish_monitor_start():
    from services.post_publish_monitor_worker import start_monitor_worker

    started = start_monitor_worker()
    return {"ok": started, "message": "monitor worker started" if started else "POST_PUBLISH_MONITOR_ENABLED=0"}


@router.get("/api/monitor/readiness")
def monitor_readiness(platform: str = Query("douyin"), account_id: str = Query("default")):
    from services.monitor_readiness import monitor_readiness_status

    return monitor_readiness_status(platform=platform, account_id=account_id)


@router.get("/api/creator/metrics")
def creator_post_metrics(
    post_url: str = Query(..., min_length=8),
    platform: str = Query("douyin"),
    account_id: str = Query("default"),
):
    from services.creator_center import fetch_creator_post_metrics

    return fetch_creator_post_metrics(platform=platform, post_url=post_url, account_id=account_id)
