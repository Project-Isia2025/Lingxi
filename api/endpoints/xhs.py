"""小红书爬虫 API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import bootstrap

bootstrap.ensure_paths()

router = APIRouter(tags=["xhs"])


@router.get("/api/xhs/status")
def xhs_crawler_status():
    from services.xhs import common as xc

    return {
        "ok": True,
        "enabled": xc.xhs_enabled(),
        "playwright_installed": xc.playwright_installed(),
        "storage_state": xc.resolve_storage_state() or None,
        "cookie_file": xc.resolve_cookie_file() or None,
        "headless": xc.playwright_headless(),
    }


@router.get("/api/xhs/search")
def xhs_search(
    keyword: str = Query(..., min_length=1, max_length=80),
    min_likes: int = Query(0, ge=0),
    limit: int = Query(15, ge=1, le=30),
):
    from services.xhs.search import search_xhs

    result = search_xhs(keyword.strip(), min_likes=min_likes, limit=limit)
    if not result.get("ok"):
        err = str(result.get("error") or "search_failed")
        if err in (
            "playwright_not_installed",
            "xhs_cookie_missing",
            "xhs_captcha_required",
            "xhs_login_required",
            "xhs_crawler_disabled",
        ):
            raise HTTPException(status_code=503, detail=result)
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/api/xhs/note")
def xhs_note_detail(url: str = Query(..., min_length=10)):
    from services.xhs.note_detail import fetch_note_detail

    result = fetch_note_detail(url.strip())
    if not result.get("ok"):
        err = str(result.get("error") or "fetch_failed")
        if err in ("playwright_not_installed", "xhs_cookie_missing", "xhs_captcha_required", "xhs_crawler_disabled"):
            raise HTTPException(status_code=503, detail=result)
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/api/xhs/note/ocr")
def xhs_note_ocr(url: str = Query(..., min_length=10)):
    from services.xhs.note_detail import fetch_note_detail

    result = fetch_note_detail(url.strip())
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return {
        "ok": True,
        "note_id": result.get("note_id"),
        "body": result.get("body"),
        "ocr_text": result.get("ocr_text"),
        "ocr": result.get("ocr"),
        "image_urls": result.get("image_urls"),
    }


@router.post("/api/ocr/image")
def ocr_image_api(url: str = Query(..., min_length=10)):
    from services.ocr import ocr_image_url

    result = ocr_image_url(url.strip())
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result)
    return result
