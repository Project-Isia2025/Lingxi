"""投流 API 客户端：巨量引擎 / 通用 OpenAPI。"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import requests

log = logging.getLogger(__name__)


def ad_api_enabled() -> bool:
    base = (os.environ.get("AD_API_BASE") or os.environ.get("OCEANENGINE_API_BASE") or "").strip()
    key = (os.environ.get("AD_API_KEY") or os.environ.get("OCEANENGINE_ACCESS_TOKEN") or "").strip()
    return bool(base and key)


def _base_url() -> str:
    return (os.environ.get("AD_API_BASE") or os.environ.get("OCEANENGINE_API_BASE") or "").strip().rstrip("/")


def _auth_headers() -> dict[str, str]:
    token = (os.environ.get("AD_API_KEY") or os.environ.get("OCEANENGINE_ACCESS_TOKEN") or "").strip()
    return {"Access-Token": token, "Content-Type": "application/json"}


def _advertiser_id() -> str:
    return (os.environ.get("OCEANENGINE_ADVERTISER_ID") or os.environ.get("AD_ADVERTISER_ID") or "").strip()


def _request(method: str, path: str, *, json_body: dict | None = None, params: dict | None = None) -> dict[str, Any]:
    url = f"{_base_url()}{path}"
    try:
        resp = requests.request(
            method,
            url,
            headers=_auth_headers(),
            json=json_body,
            params=params,
            timeout=int(os.environ.get("AD_API_TIMEOUT_SEC", "30")),
        )
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            return {"ok": False, "error": "http_error", "status": resp.status_code, "detail": data}
        if isinstance(data, dict) and data.get("code") not in (None, 0):
            return {"ok": False, "error": "api_error", "detail": data}
        return {"ok": True, "data": data.get("data", data)}
    except Exception as exc:
        return {"ok": False, "error": "request_failed", "detail": str(exc)}


def create_campaign(
    *,
    name: str,
    daily_budget_cny: float,
    platform: str = "douyin",
    keyword: str = "",
    bid_type: str = "OCPM",
) -> dict[str, Any]:
    """创建投流计划。未配置 API 时返回 dry_run 结构。"""
    if not ad_api_enabled():
        cid = f"dry_{int(time.time())}"
        return {
            "ok": True,
            "dry_run": True,
            "campaign_id": cid,
            "name": name,
            "daily_budget_cny": daily_budget_cny,
            "platform": platform,
            "bid_type": bid_type,
            "keyword": keyword,
            "message": "AD_API 未配置，已生成模拟 campaign",
        }

    advertiser_id = _advertiser_id()
    if not advertiser_id:
        return {"ok": False, "error": "advertiser_id_missing", "hint": "设置 OCEANENGINE_ADVERTISER_ID"}

    body = {
        "advertiser_id": int(advertiser_id),
        "campaign_name": name[:50],
        "budget_mode": "BUDGET_MODE_DAY",
        "budget": daily_budget_cny,
        "marketing_goal": "VIDEO_AND_IMAGE",
        "landing_type": "LINK",
    }
    result = _request("POST", "/open_api/v3.0/campaign/create/", json_body=body)
    if not result.get("ok"):
        return result
    data = result.get("data") or {}
    return {
        "ok": True,
        "dry_run": False,
        "campaign_id": str(data.get("campaign_id") or data.get("id") or ""),
        "name": name,
        "daily_budget_cny": daily_budget_cny,
        "platform": platform,
        "raw": data,
    }


def update_campaign_budget(*, campaign_id: str, daily_budget_cny: float) -> dict[str, Any]:
    if not ad_api_enabled():
        return {"ok": True, "dry_run": True, "campaign_id": campaign_id, "daily_budget_cny": daily_budget_cny}
    advertiser_id = _advertiser_id()
    body = {
        "advertiser_id": int(advertiser_id),
        "campaign_id": int(campaign_id) if str(campaign_id).isdigit() else campaign_id,
        "budget": daily_budget_cny,
        "budget_mode": "BUDGET_MODE_DAY",
    }
    return _request("POST", "/open_api/v3.0/campaign/update/", json_body=body)


def get_campaign_report(*, campaign_id: str, days: int = 7) -> dict[str, Any]:
    if not ad_api_enabled():
        return {
            "ok": True,
            "dry_run": True,
            "campaign_id": campaign_id,
            "metrics": {"impressions": 0, "clicks": 0, "cost_cny": 0, "ctr": 0},
        }
    advertiser_id = _advertiser_id()
    params = {
        "advertiser_id": advertiser_id,
        "campaign_ids": json.dumps([campaign_id]),
        "start_date": time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400)),
        "end_date": time.strftime("%Y-%m-%d"),
    }
    result = _request("GET", "/open_api/v3.0/report/campaign/get/", params=params)
    if not result.get("ok"):
        return result
    rows = (result.get("data") or {}).get("list") or []
    if not rows:
        return {"ok": True, "campaign_id": campaign_id, "metrics": {}}
    row = rows[0]
    return {
        "ok": True,
        "campaign_id": campaign_id,
        "metrics": {
            "impressions": row.get("show") or row.get("impressions"),
            "clicks": row.get("click"),
            "cost_cny": row.get("cost"),
            "ctr": row.get("ctr"),
        },
    }


def sync_ad_plan_to_api(ad_plan: dict[str, Any], *, run_id: str = "") -> dict[str, Any]:
    """将本地 ad_plan 同步到投流平台。"""
    name = f"{ad_plan.get('keyword', 'campaign')}_{run_id[:8] if run_id else 'run'}"
    daily = float(ad_plan.get("daily_budget_cny") or 100)
    created = create_campaign(
        name=name[:50],
        daily_budget_cny=daily,
        platform=str(ad_plan.get("platform") or "douyin"),
        keyword=str(ad_plan.get("keyword") or ""),
    )
    return {"create_result": created, "ad_plan": ad_plan}
