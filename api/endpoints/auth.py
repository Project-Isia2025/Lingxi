"""API 鉴权登录 / 状态。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from api.auth import API_AUTH_COOKIE, auth_status, verify_api_key
from api.auth_policy import resolve_auth_tier, tier_summary

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    api_key: str = Field(..., min_length=8, max_length=256)


@router.get("/api/auth/status")
def api_auth_status():
    return {"ok": True, **auth_status()}


@router.get("/api/auth/policy")
def api_auth_policy(method: str = "GET", path: str = "/api/health"):
    tier = resolve_auth_tier(method, path)
    return {
        "ok": True,
        "example": {"method": method.upper(), "path": path, "tier": tier.value},
        **tier_summary(),
    }


@router.post("/api/auth/login")
def api_auth_login(body: LoginRequest, response: Response):
    if not verify_api_key(body.api_key.strip()):
        raise HTTPException(status_code=401, detail={"ok": False, "error": "invalid_api_key"})
    import os

    secure = os.environ.get("ENVIRONMENT", "").strip().lower() in ("production", "prod")
    response.set_cookie(
        API_AUTH_COOKIE,
        body.api_key.strip(),
        httponly=True,
        samesite="lax",
        max_age=7 * 86400,
        secure=secure,
    )
    return {"ok": True, "message": "authenticated", "cookie": API_AUTH_COOKIE}


@router.post("/api/auth/logout")
def api_auth_logout(response: Response):
    response.delete_cookie(API_AUTH_COOKIE)
    return {"ok": True, "message": "logged_out"}
