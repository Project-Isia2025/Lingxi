"""运行时 API。"""
from __future__ import annotations

from fastapi import APIRouter, Query

import bootstrap

bootstrap.ensure_paths()

router = APIRouter(tags=["runtime"])


@router.get("/api/runtime/status")
def runtime_status_api():
    from services.runtime_status import runtime_status

    return runtime_status()


@router.get("/api/runtime/runbook")
def live_runbook_api(live: bool = Query(False), platform: str = Query("douyin")):
    from services.live_runbook import build_live_runbook

    return build_live_runbook(live=live, platform=platform)
