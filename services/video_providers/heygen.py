"""HeyGen 数字人 / 视频生成适配器（官方 v2 API）。"""
from __future__ import annotations

import os
import time
from typing import Any

from services.video_providers.http_client import (
    api_credentials,
    download_to_local,
    mock_copy_source,
    mock_image_to_video,
    poll_interval_sec,
    poll_timeout_sec,
)


def _base_url() -> str:
    return (os.environ.get("HEYGEN_API_BASE") or "https://api.heygen.com").rstrip("/")


def _generate_url() -> str:
    custom = (os.environ.get("HEYGEN_API_URL") or "").strip()
    if custom:
        return custom
    return f"{_base_url()}/v2/video/generate"


def _status_url(video_id: str) -> str:
    tpl = (os.environ.get("HEYGEN_STATUS_URL") or "").strip()
    if tpl:
        return tpl.replace("{video_id}", video_id)
    return f"{_base_url()}/v1/video_status.get?video_id={video_id}"


def build_payload(
    *,
    script: str,
    run_id: str,
    source_video: str = "",
    image_path: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ex = extra or {}
    avatar_id = (
        (os.environ.get("HEYGEN_AVATAR_ID") or ex.get("heygen_avatar_id") or ex.get("avatar_id") or "").strip()
    )
    voice_id = (
        (os.environ.get("HEYGEN_VOICE_ID") or ex.get("heygen_voice_id") or ex.get("voice_id") or "").strip()
    )
    dur = int(ex.get("duration_sec") or os.environ.get("HEYGEN_DURATION_SEC") or 15)
    payload: dict[str, Any] = {
        "provider": "heygen",
        "run_id": run_id,
        "video_inputs": [
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": avatar_id or "default",
                    "avatar_style": (os.environ.get("HEYGEN_AVATAR_STYLE") or "normal").strip(),
                },
                "voice": {
                    "type": "text",
                    "input_text": script[:2000],
                    "voice_id": voice_id or "default",
                },
            }
        ],
        "dimension": {"width": 1080, "height": 1920},
        "aspect_ratio": "9:16",
        "duration": dur,
        "test": os.environ.get("HEYGEN_TEST_MODE", "0").strip().lower() in ("1", "true", "yes"),
    }
    if source_video:
        payload["background_video"] = source_video
    if image_path:
        payload["product_image"] = image_path
    if ex:
        payload["extra"] = ex
    return payload


def _extract_video_id(data: dict[str, Any]) -> str:
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    return str(
        data.get("video_id")
        or data.get("id")
        or inner.get("video_id")
        or inner.get("id")
        or ""
    ).strip()


def _extract_video_url(data: dict[str, Any]) -> str:
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    return str(
        data.get("video_url")
        or data.get("output_url")
        or inner.get("video_url")
        or inner.get("video_url_caption")
        or inner.get("url")
        or ""
    ).strip()


def produce(
    *,
    script: str,
    run_id: str,
    source_video: str = "",
    image_path: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    api_key, _ = api_credentials("heygen")
    payload = build_payload(
        script=script,
        run_id=run_id,
        source_video=source_video,
        image_path=image_path,
        extra=extra,
    )
    if not api_key:
        dur = float(payload.get("duration") or 15)
        if image_path:
            out = mock_image_to_video(provider="heygen", run_id=run_id, image_path=image_path, duration_sec=dur)
            if out.get("ok"):
                out["heygen"] = {"mode": "mock_image"}
                return out
        out = mock_copy_source(
            provider="heygen",
            run_id=run_id,
            source_video=source_video,
            hint="配置 HEYGEN_API_KEY 或提供 product_image/source_video 进行 mock",
        )
        out["heygen"] = {"mode": out.get("mode")}
        return out

    import requests

    headers = {"X-Api-Key": api_key, "Content-Type": "application/json"}
    generate_url = _generate_url()
    try:
        resp = requests.post(generate_url, json=payload, headers=headers, timeout=45)
        if resp.status_code >= 400:
            return {
                "ok": False,
                "error": "heygen_api_error",
                "status": resp.status_code,
                "body": resp.text[:300],
            }
        data = resp.json() if resp.content else {}
    except Exception as exc:
        return {"ok": False, "error": "heygen_request_failed", "detail": str(exc)[:300]}

    direct_url = _extract_video_url(data)
    if direct_url:
        out = download_to_local(direct_url, run_id=run_id, provider="heygen")
        out["heygen"] = {"mode": "api_direct"}
        return out

    video_id = _extract_video_id(data)
    if not video_id:
        return {"ok": False, "error": "heygen_no_video_id", "response": data}

    status_url = _status_url(video_id)
    deadline = time.time() + poll_timeout_sec()
    while time.time() < deadline:
        time.sleep(poll_interval_sec())
        try:
            pr = requests.get(status_url, headers=headers, timeout=25)
            pdata = pr.json() if pr.content else {}
        except Exception as exc:
            return {"ok": False, "error": "heygen_poll_failed", "detail": str(exc)[:200], "video_id": video_id}
        status = str(
            pdata.get("status") or pdata.get("state") or (pdata.get("data") or {}).get("status") or ""
        ).lower()
        url = _extract_video_url(pdata)
        if url and status in ("", "success", "succeeded", "done", "completed", "complete"):
            out = download_to_local(url, run_id=run_id, provider="heygen", task_id=video_id)
            out["heygen"] = {"mode": "api_poll", "video_id": video_id}
            return out
        if status in ("failed", "error", "cancelled"):
            return {"ok": False, "error": "heygen_task_failed", "video_id": video_id, "response": pdata}

    return {"ok": False, "error": "heygen_timeout", "video_id": video_id}
