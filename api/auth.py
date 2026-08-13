"""HTTP 指标 + API 鉴权中间件（按路由分级）。"""
from __future__ import annotations

import hmac
import logging
import os
import time

from fastapi import Request, WebSocket
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from api.auth_policy import AuthTier, requires_admin_key, requires_api_key, resolve_auth_tier, tier_summary

log = logging.getLogger(__name__)

API_AUTH_COOKIE = "matrix_api_key"
_AUTH_SCRIPT = '<script src="/static/matrix-auth.js"></script>'

_TRUE = frozenset({"1", "true", "yes", "on"})


def _is_production() -> bool:
    return os.environ.get("ENVIRONMENT", "development").strip().lower() in ("production", "prod")


def _allow_query_api_key() -> bool:
    if not _is_production():
        return True
    return os.environ.get("API_AUTH_ALLOW_QUERY_KEY", "0").strip().lower() in _TRUE


def auth_enabled() -> bool:
    return os.environ.get("API_AUTH_ENABLED", "0").strip().lower() in _TRUE


def configured_keys() -> list[str]:
    raw = (os.environ.get("API_AUTH_KEY") or os.environ.get("MATRIX_API_KEY") or "").strip()
    if not raw:
        return []
    return [k.strip() for k in raw.split(",") if k.strip()]


def configured_admin_keys() -> list[str]:
    raw = (os.environ.get("API_AUTH_ADMIN_KEY") or "").strip()
    if not raw:
        return []
    return [k.strip() for k in raw.split(",") if k.strip()]


def extract_api_key(request: Request | WebSocket) -> str:
    allow_query = _allow_query_api_key()
    if isinstance(request, WebSocket):
        cookie = request.cookies.get(API_AUTH_COOKIE) or ""
        if cookie:
            return cookie.strip()
        if allow_query:
            qp = request.query_params.get("api_key") or request.query_params.get("token") or ""
            if qp:
                return str(qp).strip()
        header = request.headers.get("X-API-Key") or request.headers.get("Authorization") or ""
    else:
        if allow_query:
            qp = request.query_params.get("api_key") or ""
            if qp:
                return str(qp).strip()
        header = request.headers.get("X-API-Key") or request.headers.get("Authorization") or ""
        cookie = request.cookies.get(API_AUTH_COOKIE) or ""
        if cookie:
            return cookie.strip()

    header = (header or "").strip()
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return header.strip()


def _keys_match(key: str, candidates: list[str]) -> bool:
    if not key or not candidates:
        return False
    return any(hmac.compare_digest(key, candidate) for candidate in candidates)


def verify_api_key(key: str) -> bool:
    return _keys_match(key, configured_keys())


def verify_admin_key(key: str) -> bool:
    admin_keys = configured_admin_keys()
    if admin_keys:
        return _keys_match(key, admin_keys)
    return verify_api_key(key)


def verify_key_for_tier(key: str, tier: AuthTier) -> bool:
    if not requires_api_key(tier):
        return True
    if requires_admin_key(tier, admin_key_configured=bool(configured_admin_keys())):
        return verify_admin_key(key)
    return verify_api_key(key)


def auth_status() -> dict[str, object]:
    keys = configured_keys()
    admin_keys = configured_admin_keys()
    return {
        "enabled": auth_enabled(),
        "configured": bool(keys),
        "key_count": len(keys),
        "admin_key_configured": bool(admin_keys),
        "admin_key_count": len(admin_keys),
        "cookie_name": API_AUTH_COOKIE,
        "header": "X-API-Key",
        "bearer": True,
        "policy": tier_summary(),
    }


def is_public_path(method: str, path: str) -> bool:
    """兼容旧调用：非 protected tier 视为 public。"""
    return not requires_api_key(resolve_auth_tier(method, path))


def inject_auth_script(html: str) -> str:
    if not auth_enabled() or _AUTH_SCRIPT in html:
        return html
    if "</head>" in html:
        return html.replace("</head>", f"  {_AUTH_SCRIPT}\n</head>", 1)
    return _AUTH_SCRIPT + html


async def verify_websocket_auth(websocket: WebSocket) -> bool:
    if not auth_enabled():
        return True
    tier = resolve_auth_tier("GET", websocket.url.path)
    if not requires_api_key(tier):
        return True
    return verify_key_for_tier(extract_api_key(websocket), tier)


def _unauthorized_response(tier: AuthTier) -> JSONResponse:
    admin_required = requires_admin_key(tier, admin_key_configured=bool(configured_admin_keys()))
    hint = (
        "Admin API key required for this route (API_AUTH_ADMIN_KEY)"
        if admin_required
        else "Provide X-API-Key header, Authorization: Bearer, api_key query, or POST /api/auth/login"
    )
    return JSONResponse(
        status_code=401 if not admin_required else 403,
        content={
            "ok": False,
            "error": "forbidden" if admin_required else "unauthorized",
            "tier": tier.value,
            "hint": hint,
        },
    )


def _metric_path(path: str) -> str:
    parts = [p for p in path.split("/") if p][:3]
    return "/" + "/".join(parts) if parts else path


class ApiAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        method = request.method.upper()
        endpoint = _metric_path(path)
        started = time.perf_counter()
        status_code = 500

        try:
            tier = resolve_auth_tier(method, path)
            if auth_enabled() and requires_api_key(tier):
                key = extract_api_key(request)
                if not verify_key_for_tier(key, tier):
                    status_code = 403 if tier == AuthTier.ADMIN and configured_admin_keys() else 401
                    return _unauthorized_response(tier)

                response = await call_next(request)
                status_code = response.status_code
                if key and request.headers.get("X-API-Key") and API_AUTH_COOKIE not in request.cookies:
                    secure = os.environ.get("ENVIRONMENT", "").strip().lower() in ("production", "prod")
                    response.set_cookie(
                        API_AUTH_COOKIE,
                        key,
                        httponly=True,
                        samesite="lax",
                        max_age=7 * 86400,
                        secure=secure,
                    )
                return response

            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            try:
                from infra.metrics import record_request

                record_request(
                    method=method,
                    endpoint=endpoint,
                    status=status_code,
                    duration_sec=time.perf_counter() - started,
                )
            except Exception:
                pass
