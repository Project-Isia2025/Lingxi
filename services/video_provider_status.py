"""AI 视频 Provider 凭证与就绪状态检查。"""
from __future__ import annotations

import os
from typing import Any

from services.video_providers.http_client import api_credentials
from services.video_providers.router import list_providers, video_gen_enabled


def _extra_env_keys(provider: str) -> dict[str, str]:
    pid = provider.strip().upper()
    keys = {
        "avatar": ["AVATAR_CLONE_ID", "AVATAR_VOICE_ID", "AVATAR_STYLE", "AVATAR_DURATION_SEC"],
        "volc": ["VOLC_MODEL", "VOLC_DURATION_SEC"],
        "kling": ["KLING_MODEL", "KLING_DURATION_SEC"],
        "heygen": ["HEYGEN_AVATAR_ID", "HEYGEN_VOICE_ID", "HEYGEN_API_BASE", "HEYGEN_DURATION_SEC"],
        "capcut": ["CAPCUT_TEMPLATE_ID", "CAPCUT_DURATION_SEC", "JIANYING_TEMPLATE_ID"],
        "jianying": ["JIANYING_TEMPLATE_ID", "JIANYING_API_URL"],
    }
    out: dict[str, str] = {}
    for key in keys.get(provider.lower(), []):
        val = (os.environ.get(key) or "").strip()
        if val:
            out[key] = val
    return out


def provider_status(provider: str) -> dict[str, Any]:
    """检查单个 provider 的 API 配置（不暴露 key 明文）。"""
    pid = (provider or "").strip().lower()
    api_key, api_url = api_credentials(pid)
    has_key = bool(api_key)
    has_url = bool(api_url)
    configured = has_key and has_url
    return {
        "provider": pid,
        "configured": configured,
        "has_key": has_key,
        "has_url": has_url,
        "key_preview": f"{api_key[:4]}***" if len(api_key) >= 4 else ("set" if has_key else ""),
        "api_url": api_url or "",
        "mode": "live" if configured else "mock",
        "extra": _extra_env_keys(pid),
    }


def all_providers_status() -> dict[str, Any]:
    rows = [provider_status(p) for p in list_providers()]
    configured = [r["provider"] for r in rows if r.get("configured")]
    return {
        "ok": True,
        "video_gen_enabled": video_gen_enabled(),
        "providers": rows,
        "configured": configured,
        "mock_only": [r["provider"] for r in rows if not r.get("configured")],
        "live_ready": len(configured) > 0,
    }
