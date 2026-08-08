"""AI 视频生成 API。"""
from __future__ import annotations

from fastapi import APIRouter, Query

import bootstrap

bootstrap.ensure_paths()

router = APIRouter(tags=["video"])


@router.get("/api/video/providers")
def video_providers():
    from services.video_providers.router import list_providers, video_gen_enabled

    return {"ok": True, "enabled": video_gen_enabled(), "providers": list_providers()}


@router.get("/api/video/providers/status")
def video_providers_status():
    from services.video_provider_status import all_providers_status

    return all_providers_status()


@router.post("/api/video/produce")
def video_produce(
    script: str = Query(..., min_length=4),
    provider: str = Query("avatar"),
    run_id: str = Query("api-produce"),
    source_video: str = Query(""),
    image_path: str = Query(""),
):
    from services.video_providers.router import produce_video

    return produce_video(
        provider=provider,
        script=script,
        run_id=run_id,
        source_video=source_video,
        image_path=image_path,
    )
