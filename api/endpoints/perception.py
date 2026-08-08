"""数据感知调度 API。"""
from __future__ import annotations

from fastapi import APIRouter, Query

import bootstrap

bootstrap.ensure_paths()

router = APIRouter(tags=["perception"])


@router.get("/api/perception/status")
def perception_status():
    from services.perception_scheduler import get_scheduler_status

    return get_scheduler_status()


@router.post("/api/perception/scan")
def perception_scan(keyword: str = Query("", max_length=80)):
    from services.perception_scheduler import run_scheduled_perception

    return run_scheduled_perception(keyword=keyword or None)


@router.post("/api/perception/start")
def perception_start():
    from services.perception_scheduler import start_perception_scheduler

    started = start_perception_scheduler()
    return {"ok": started, "message": "perception scheduler started" if started else "PERCEPTION_SCHEDULE_ENABLED=0"}


@router.get("/api/douyin/hotlist")
def douyin_hotlist(limit: int = Query(20, ge=1, le=50)):
    from services.douyin.hotlist import fetch_douyin_hotlist

    return fetch_douyin_hotlist(limit=limit)


@router.get("/api/inventory")
def inventory_list(org_id: str = ""):
    from services.inventory import list_products

    products = list_products(org_id=org_id.strip())
    return {"ok": True, "count": len(products), "org_id": org_id.strip(), "products": products}
