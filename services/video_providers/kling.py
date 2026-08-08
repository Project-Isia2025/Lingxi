"""可灵 Kling 视频生成适配器。"""
from __future__ import annotations

import os
from typing import Any

from services.video_providers.http_client import api_credentials, http_produce_task, mock_copy_source


def build_payload(
    *,
    script: str,
    run_id: str,
    source_video: str = "",
    image_path: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dur = int((extra or {}).get("duration_sec") or os.environ.get("KLING_DURATION_SEC") or 15)
    model = (os.environ.get("KLING_MODEL") or (extra or {}).get("kling_model") or "kling-v1").strip()
    return {
        "provider": "kling",
        "run_id": run_id,
        "prompt": script[:2000],
        "script": script[:2000],
        "reference_video": source_video,
        "reference_image": image_path,
        "image_url": image_path,
        "duration": dur,
        "model": model,
        "aspect_ratio": "9:16",
        "mode": (extra or {}).get("kling_mode") or "std",
        "extra": extra or {},
    }


def produce(
    *,
    script: str,
    run_id: str,
    source_video: str = "",
    image_path: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    api_key, api_url = api_credentials("kling")
    payload = build_payload(
        script=script,
        run_id=run_id,
        source_video=source_video,
        image_path=image_path,
        extra=extra,
    )
    if api_key and api_url:
        return http_produce_task(provider="kling", api_url=api_url, api_key=api_key, payload=payload, run_id=run_id)
    return mock_copy_source(provider="kling", run_id=run_id, source_video=source_video)
