"""数字人 / Avatar 视频生成适配器。"""
from __future__ import annotations

import os
from typing import Any

from services.video_providers.http_client import (
    api_credentials,
    http_produce_task,
    mock_copy_source,
    mock_image_to_video,
)


def build_payload(
    *,
    script: str,
    run_id: str,
    source_video: str = "",
    image_path: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dur = int((extra or {}).get("duration_sec") or os.environ.get("AVATAR_DURATION_SEC") or 15)
    payload: dict[str, Any] = {
        "provider": "avatar",
        "run_id": run_id,
        "speech_text": script[:2000],
        "script": script[:2000],
        "avatar_image": image_path,
        "product_image": image_path,
        "background_video": source_video,
        "reference_video": source_video,
        "duration": dur,
        "aspect_ratio": "9:16",
        "resolution": "1080x1920",
    }
    clone_id = (os.environ.get("AVATAR_CLONE_ID") or (extra or {}).get("avatar_clone_id") or "").strip()
    voice_id = (os.environ.get("AVATAR_VOICE_ID") or (extra or {}).get("avatar_voice_id") or "").strip()
    if clone_id:
        payload["avatar_id"] = clone_id
        payload["clone_id"] = clone_id
    if voice_id:
        payload["voice_id"] = voice_id
        payload["tts_voice"] = voice_id
    style = (os.environ.get("AVATAR_STYLE") or (extra or {}).get("avatar_style") or "talking_head").strip()
    payload["style"] = style
    if extra:
        payload["extra"] = extra
    return payload


def produce(
    *,
    script: str,
    run_id: str,
    source_video: str = "",
    image_path: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    api_key, api_url = api_credentials("avatar")
    payload = build_payload(
        script=script,
        run_id=run_id,
        source_video=source_video,
        image_path=image_path,
        extra=extra,
    )
    if api_key and api_url:
        result = http_produce_task(
            provider="avatar",
            api_url=api_url,
            api_key=api_key,
            payload=payload,
            run_id=run_id,
        )
        result["avatar"] = {"clone_id": payload.get("avatar_id"), "voice_id": payload.get("voice_id")}
        return result

    dur = float(payload.get("duration") or 15)
    if image_path:
        out = mock_image_to_video(provider="avatar", run_id=run_id, image_path=image_path, duration_sec=dur)
        if out.get("ok"):
            out["avatar"] = {"mode": "mock_image", "clone_id": payload.get("avatar_id")}
            return out
    out = mock_copy_source(
        provider="avatar",
        run_id=run_id,
        source_video=source_video,
        hint="配置 AVATAR_API_KEY/URL 或提供 product_image/source_video 进行 mock",
    )
    out["avatar"] = {"mode": out.get("mode"), "clone_id": payload.get("avatar_id")}
    return out
