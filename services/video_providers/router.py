"""AI 视频生成 provider 路由。"""
from __future__ import annotations

import os
from typing import Any

from services.strategy import LOW_COST
from services.video_providers import avatar, capcut, heygen, kling, volc
from services.video_providers.http_client import api_credentials, http_produce_task, mock_copy_source

PROVIDER_REGISTRY = {
    "avatar": avatar,
    "capcut": capcut,
    "heygen": heygen,
    "jianying": capcut,
    "kling": kling,
    "volc": volc,
}


def video_gen_enabled() -> bool:
    return os.environ.get("VIDEO_GEN_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def poll_timeout_sec() -> float:
    from services.video_providers.http_client import poll_timeout_sec as _t

    return _t()


def poll_interval_sec() -> float:
    from services.video_providers.http_client import poll_interval_sec as _i

    return _i()


def list_providers() -> list[str]:
    return sorted(PROVIDER_REGISTRY.keys())


def produce_video(
    *,
    provider: str,
    script: str,
    run_id: str,
    source_video: str = "",
    image_path: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pid = (provider or "template").strip().lower()
    if not video_gen_enabled() or pid in LOW_COST or pid == "template":
        return {"ok": False, "reason": "provider_not_ai", "provider": pid}

    mod = PROVIDER_REGISTRY.get(pid)
    if mod and hasattr(mod, "produce"):
        return mod.produce(
            script=script,
            run_id=run_id,
            source_video=source_video,
            image_path=image_path,
            extra=extra,
        )

    api_key, api_url = api_credentials(pid)
    if api_key and api_url:
        payload = {
            "script": script[:2000],
            "run_id": run_id,
            "source_video": source_video,
            "image_path": image_path,
            "provider": pid,
            "extra": extra or {},
        }
        return http_produce_task(
            provider=pid,
            api_url=api_url,
            api_key=api_key,
            payload=payload,
            run_id=run_id,
        )
    return mock_copy_source(provider=pid, run_id=run_id, source_video=source_video)
