"""剪映 / CapCut 开放平台视频生成适配器。"""
from __future__ import annotations

import os
from typing import Any

from services.video_providers.http_client import (
    api_credentials,
    http_produce_task,
    mock_copy_source,
    mock_image_to_video,
)


def _resolve_credentials() -> tuple[str, str]:
    key = (os.environ.get("CAPCUT_API_KEY") or os.environ.get("JIANYING_API_KEY") or "").strip()
    url = (os.environ.get("CAPCUT_API_URL") or os.environ.get("JIANYING_API_URL") or "").strip()
    if key and url:
        return key, url
    return api_credentials("capcut")


def build_payload(
    *,
    script: str,
    run_id: str,
    source_video: str = "",
    image_path: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ex = extra or {}
    template_id = (
        (os.environ.get("CAPCUT_TEMPLATE_ID") or os.environ.get("JIANYING_TEMPLATE_ID") or ex.get("template_id") or "")
        .strip()
    )
    dur = int(ex.get("duration_sec") or os.environ.get("CAPCUT_DURATION_SEC") or os.environ.get("JIANYING_DURATION_SEC") or 15)
    return {
        "provider": "capcut",
        "run_id": run_id,
        "template_id": template_id,
        "script": script[:2000],
        "text": script[:2000],
        "subtitle": script[:500],
        "materials": {
            "video": source_video,
            "image": image_path,
            "product_image": image_path,
            "reference_video": source_video,
        },
        "duration": dur,
        "aspect_ratio": "9:16",
        "resolution": "1080x1920",
        "output_format": "mp4",
        "extra": ex,
    }


def produce(
    *,
    script: str,
    run_id: str,
    source_video: str = "",
    image_path: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    api_key, api_url = _resolve_credentials()
    payload = build_payload(
        script=script,
        run_id=run_id,
        source_video=source_video,
        image_path=image_path,
        extra=extra,
    )
    if api_key and api_url:
        auth = (os.environ.get("CAPCUT_AUTH_HEADER") or "Bearer").strip()
        result = http_produce_task(
            provider="capcut",
            api_url=api_url,
            api_key=api_key,
            payload=payload,
            run_id=run_id,
            auth_header=auth,
        )
        result["capcut"] = {"template_id": payload.get("template_id"), "mode": "api"}
        return result

    dur = float(payload.get("duration") or 15)
    if image_path:
        out = mock_image_to_video(provider="capcut", run_id=run_id, image_path=image_path, duration_sec=dur)
        if out.get("ok"):
            out["capcut"] = {"mode": "mock_image", "template_id": payload.get("template_id")}
            return out
    out = mock_copy_source(
        provider="capcut",
        run_id=run_id,
        source_video=source_video,
        hint="配置 CAPCUT_API_KEY/CAPCUT_API_URL 或提供 source_video 进行 mock",
    )
    out["capcut"] = {"mode": out.get("mode"), "template_id": payload.get("template_id")}
    return out
