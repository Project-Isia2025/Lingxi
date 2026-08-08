"""多 org Webhook / Runbook 告警 API。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

import bootstrap

bootstrap.ensure_paths()

router = APIRouter(tags=["org"])


class OrgWebhookPatch(BaseModel):
    label: str = ""
    review_webhook_url: str = ""
    alert_webhook_url: str = ""
    runbook_webhook_url: str = ""
    review_base_url: str = ""
    enabled: bool | None = None


@router.get("/api/orgs/webhooks/status")
def org_webhooks_status(org_id: str = Query("")):
    from services.org_webhook_config import all_org_webhooks_status, org_webhook_status

    if org_id.strip():
        return org_webhook_status(org_id)
    return all_org_webhooks_status()


@router.post("/api/orgs/{org_id}/webhooks")
def upsert_org_webhooks(org_id: str, body: OrgWebhookPatch):
    from services.org_webhook_config import upsert_org_config

    patch = body.model_dump(exclude_none=True)
    return upsert_org_config(org_id, patch)


@router.post("/api/runtime/runbook/alert")
def runbook_alert_api(
    org_id: str = Query(""),
    platform: str = Query("douyin"),
    live: bool = Query(False),
    dry_run: bool = Query(True),
    force: bool = Query(False),
):
    from services.live_runbook import build_live_runbook
    from services.runbook_alert import dispatch_runbook_alert

    runbook = build_live_runbook(live=live, platform=platform)
    alert = dispatch_runbook_alert(
        runbook=runbook,
        org_id=org_id,
        platform=platform,
        dry_run=dry_run,
        force=force,
    )
    return {"ok": True, "runbook_ok": runbook.get("ok"), "runbook": runbook, "alert": alert}


@router.get("/api/runtime/runbook/alert/status")
def runbook_alert_status():
    from services.runbook_alert import runbook_alert_enabled, runbook_alert_min_failures

    return {
        "ok": True,
        "enabled": runbook_alert_enabled(),
        "min_failures": runbook_alert_min_failures(),
    }
