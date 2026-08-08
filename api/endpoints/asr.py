"""ASR 转写 API。"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import bootstrap

bootstrap.ensure_paths()

router = APIRouter(tags=["asr"])


class AsrTranscribePayload(BaseModel):
    video_path: str = Field(default="", description="本地视频路径")
    video_url: str = Field(default="", description="远程视频 URL")
    save_to_memory: bool = Field(default=True, description="转写成功后写入知识库")
    title: str = Field(default="", description="记忆库标题")
    keyword: str = Field(default="")
    run_id: str = Field(default="")


@router.get("/api/asr/status")
def asr_status():
    from services.asr import asr_enabled, resolve_ffmpeg

    return {
        "ok": True,
        "enabled": asr_enabled(),
        "ffmpeg": resolve_ffmpeg(),
        "api_configured": bool(
            (os.environ.get("ASR_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
        ),
    }


@router.post("/api/asr/transcribe")
def asr_transcribe(body: AsrTranscribePayload):
    from services.asr import transcribe_url, transcribe_video

    if body.video_path.strip():
        result = transcribe_video(body.video_path.strip())
    elif body.video_url.strip():
        result = transcribe_url(body.video_url.strip())
    else:
        raise HTTPException(status_code=400, detail={"error": "video_path_or_url_required"})
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result)
    if body.save_to_memory and result.get("text"):
        from services.asr_memory import ingest_asr_transcript

        result["memory"] = ingest_asr_transcript(
            text=result["text"],
            title=body.title or "视频转写",
            source_url=body.video_url,
            run_id=body.run_id,
            keyword=body.keyword,
        )
    return result


@router.post("/api/asr/transcribe/url")
def asr_transcribe_url(video_url: str = Query(..., min_length=10)):
    from services.asr import transcribe_url

    result = transcribe_url(video_url.strip())
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result)
    return result
