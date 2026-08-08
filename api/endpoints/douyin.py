"""抖音爬虫 API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import bootstrap

bootstrap.ensure_paths()

router = APIRouter(tags=["douyin"])


@router.get("/api/douyin/status")
def douyin_crawler_status():
    from services.douyin import common as dc

    return {
        "ok": True,
        "enabled": dc.douyin_enabled(),
        "playwright_installed": dc.playwright_installed(),
        "storage_state": dc.resolve_storage_state() or None,
        "cookie_file": dc.resolve_cookie_file() or None,
        "headless": dc.playwright_headless(),
    }


@router.get("/api/douyin/search")
def douyin_search(
    keyword: str = Query(..., min_length=1, max_length=80),
    min_likes: int = Query(0, ge=0),
    min_followers: int = Query(0, ge=0),
    limit: int = Query(15, ge=1, le=30),
):
    from services.douyin.search import search_douyin

    result = search_douyin(
        keyword.strip(),
        min_likes=min_likes,
        min_followers=min_followers,
        limit=limit,
    )
    if not result.get("ok"):
        err = str(result.get("error") or "search_failed")
        if err in (
            "playwright_not_installed",
            "douyin_cookie_missing",
            "douyin_captcha_required",
            "douyin_login_required",
            "douyin_crawler_disabled",
        ):
            raise HTTPException(status_code=503, detail=result)
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/api/douyin/video/{video_id}")
def douyin_video_detail(video_id: str):
    from services.douyin.video_detail import fetch_video_detail

    result = fetch_video_detail(video_id)
    if not result.get("ok"):
        err = str(result.get("error") or "detail_failed")
        if err in ("douyin_crawler_unavailable", "douyin_cookie_missing", "douyin_captcha_required"):
            raise HTTPException(status_code=503, detail=result)
        raise HTTPException(status_code=400, detail=result)
    return result
