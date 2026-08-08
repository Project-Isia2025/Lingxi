"""影刀 / 八爪鱼 RPA Webhook 接入。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

import bootstrap

bootstrap.ensure_paths()

from api.auth import inject_auth_script

router = APIRouter(tags=["rpa"])
_RPA_SETUP_HTML = inject_auth_script(Path(__file__).with_name("rpa_setup.html").read_text(encoding="utf-8"))


def _token_from_request(request: Request, header_token: str, query_token: str) -> str:
    if query_token:
        return query_token.strip()
    if header_token:
        return header_token.strip()
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("X-RPA-Webhook-Token") or request.headers.get("X-Webhook-Token") or "").strip()


@router.get("/dashboard/rpa", response_class=HTMLResponse)
def rpa_setup_dashboard():
    return HTMLResponse(_RPA_SETUP_HTML)


@router.get("/api/rpa/guide")
def rpa_integration_guide(request: Request):
    from services.rpa_ingest import build_rpa_integration_guide

    base = str(request.base_url).rstrip("/")
    return build_rpa_integration_guide(base_url=base)


@router.get("/api/rpa/status")
def rpa_status():
    from services.rpa_ingest import rpa_ingest_status

    return rpa_ingest_status()


@router.get("/api/rpa/records")
def rpa_records(
    limit: int = Query(20, ge=1, le=100),
    platform: str = Query(""),
    keyword: str = Query(""),
):
    from services.rpa_ingest import list_rpa_records

    return {"ok": True, "records": list_rpa_records(limit=limit, platform=platform, keyword=keyword)}


@router.post("/api/rpa/webhook")
async def rpa_webhook(
    request: Request,
    source: str = Query("generic"),
    token: str = Query(""),
    x_rpa_webhook_token: str = Header(default="", alias="X-RPA-Webhook-Token"),
):
    from services.rpa_ingest import ingest_rpa_webhook

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {"data": payload}
    tok = _token_from_request(request, x_rpa_webhook_token, token)
    return ingest_rpa_webhook(payload, source=source, token=tok)


@router.post("/api/rpa/webhook/yingdao")
async def yingdao_webhook(
    request: Request,
    token: str = Query(""),
    x_rpa_webhook_token: str = Header(default="", alias="X-RPA-Webhook-Token"),
):
    from services.rpa_ingest import ingest_rpa_webhook

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {"data": payload}
    payload.setdefault("source", "yingdao")
    tok = _token_from_request(request, x_rpa_webhook_token, token)
    return ingest_rpa_webhook(payload, source="yingdao", token=tok)


@router.post("/api/rpa/webhook/octoparse")
async def octoparse_webhook(
    request: Request,
    token: str = Query(""),
    x_rpa_webhook_token: str = Header(default="", alias="X-RPA-Webhook-Token"),
):
    from services.rpa_ingest import ingest_rpa_webhook

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {"data": payload}
    payload.setdefault("source", "octoparse")
    tok = _token_from_request(request, x_rpa_webhook_token, token)
    return ingest_rpa_webhook(payload, source="octoparse", token=tok)


@router.post("/api/rpa/setup/init-mapping")
def rpa_init_mapping(force: bool = Query(False)):
    from services.rpa_ingest import init_field_mapping_file

    return init_field_mapping_file(force=force)


@router.post("/api/rpa/test-ingest")
async def rpa_test_ingest():
    """向感知层写入一条测试数据（无需影刀，用于联调）。仅 DEBUG=1 时可用。"""
    import json
    import os

    if os.environ.get("DEBUG", "0").strip().lower() not in ("1", "true", "yes", "on"):
        raise HTTPException(status_code=403, detail="test-ingest disabled; set DEBUG=1 to enable")

    from services.rpa_ingest import ingest_rpa_webhook

    example_path = bootstrap.project_root() / "data" / "yingdao_webhook.example.json"
    if example_path.is_file():
        payload = json.loads(example_path.read_text(encoding="utf-8"))
    else:
        payload = {
            "platform": "douyin",
            "keyword": "联调测试",
            "items": [{"title": "影刀联调测试视频", "url": "https://example.com/test", "likes": 999}],
        }
    payload["task_id"] = "dashboard-test"
    return ingest_rpa_webhook(payload, source="yingdao", token="")
