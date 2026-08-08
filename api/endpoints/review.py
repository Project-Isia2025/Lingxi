"""成片审核 API + 简易打回页。"""
from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

import bootstrap

bootstrap.ensure_paths()

router = APIRouter(tags=["review"])


class RejectBody(BaseModel):
    reason: str = Field(..., min_length=2, max_length=500)


@router.post("/api/review/callback")
async def review_callback(request: Request):
    """飞书卡片 action 回调 / URL 验证 / 通用 JSON。"""
    from services.feishu_review import handle_review_callback

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    result = handle_review_callback(body)
    if "challenge" in result:
        return JSONResponse(result)
    if result.get("toast"):
        return JSONResponse(result)
    if not result.get("ok") and result.get("error"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/api/review/status")
def review_status(limit: int = Query(20, ge=1, le=100)):
    from services.review_queue import get_review_status

    return get_review_status(limit=limit)


@router.delete("/api/review/{review_id}")
def review_delete(review_id: str):
    from services.review_queue import delete_review_item

    result = delete_review_item(review_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return {"ok": True, "message": "审核记录已删除", **result}


@router.get("/api/review/feishu/status")
def review_feishu_status():
    from services.feishu_review_status import feishu_review_status

    return feishu_review_status()


@router.get("/api/storage/status")
def storage_status():
    from services.storage_state_wizard import all_storage_status

    return all_storage_status()


@router.post("/api/review/submit")
def review_submit(
    run_id: str = Query(...),
    video_path: str = Query(...),
    script: str = Query(""),
    title: str = Query(""),
):
    from services.review_queue import submit_for_review

    return submit_for_review(run_id=run_id, video_path=video_path, script=script, title=title)


@router.get("/api/review/{review_id}/approve")
def review_approve(review_id: str, token: str = Query("")):
    from services.review_queue import approve_review

    result = approve_review(review_id=review_id, token=token)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/api/review/{review_id}/reject")
def review_reject(review_id: str, body: RejectBody, token: str = Query("")):
    from services.review_queue import reject_review

    result = reject_review(review_id=review_id, reason=body.reason, token=token)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/api/review/{review_id}/reject-form")
def review_reject_form(review_id: str, reason: str = Form(...), token: str = Query("")):
    from services.review_queue import reject_review

    result = reject_review(review_id=review_id, reason=reason, token=token)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return HTMLResponse(
        f"<h3>已打回</h3><p>{result.get('review_id')}</p><pre>{result}</pre>",
        status_code=200,
    )


@router.get("/api/content/slice-drafts")
def preview_slice_drafts(
    keyword: str = Query("护肤"),
    script: str = Query("测试口播素材。痛点描述。解决方案。"),
):
    """预览 3×15s 切片初稿（脚本 + mix_plan，不渲染）。"""
    from services.daily_directive import build_daily_directive
    from services.slice_drafts import generate_slice_drafts
    from services.strategy import build_strategy

    perception: dict = {"hotspots": [], "hotlist": [], "competitors": []}
    memory: dict = {"geo": {}, "forbidden_rows": []}
    strategy = build_strategy(
        keyword=keyword,
        platform="douyin",
        perception=perception,
        memory=memory,
        budget_limit=5.0,
        video_provider="template",
    )
    daily = strategy.get("daily_directive") or build_daily_directive(keyword=keyword, perception=perception)
    strategy["daily_directive"] = daily
    return generate_slice_drafts(
        base_script=script,
        keyword=keyword,
        strategy=strategy,
        product_name=str((daily.get("primary_product") or {}).get("name") or keyword),
    )


@router.get("/api/review/run/{run_id}/slices")
def review_run_slices(run_id: str):
    from services.slice_publish import slice_batch_status

    return slice_batch_status(run_id=run_id)


@router.post("/api/review/run/{run_id}/approve-all-slices")
def review_approve_all_slices(run_id: str, token: str = Query("")):
    from services.slice_publish import approve_all_pending_slices

    result = approve_all_pending_slices(run_id=run_id, token=token)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/api/review/batch-card/preview")
def preview_batch_review_card(
    run_id: str = Query("run-preview"),
    keyword: str = Query("A面膜"),
):
    """预览 3 切片合并飞书审核卡片 JSON（不发送）。"""
    from services.feishu_review import build_slice_batch_review_card, review_token

    items = []
    for sid, hook in [("S1", "痛点反问"), ("S2", "结果先行"), ("S3", "对比冲击")]:
        rid = f"rev-preview-{sid.lower()}"
        items.append({
            "review_id": rid,
            "slice_id": sid,
            "hook_style": hook,
            "script": f"15秒切片{sid}口播脚本示例",
            "video_path": f"data/output/videos/slice_{sid}.mp4",
            "token": review_token(rid),
        })
    return build_slice_batch_review_card(
        run_id=run_id,
        title=f"{keyword}·Campaign",
        items=items,
        keyword=keyword,
        platform="douyin",
    )


@router.get("/dashboard/review", response_class=HTMLResponse)
def review_reject_page(review_id: str = Query(""), token: str = Query("")):
    if not review_id:
        return HTMLResponse("<h3>缺少 review_id</h3>", status_code=400)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>打回审核</title>
<style>body{{font-family:sans-serif;max-width:640px;margin:40px auto;padding:0 16px}}
textarea{{width:100%;min-height:120px}}button{{padding:8px 16px;background:#e74c3c;color:#fff;border:0;border-radius:4px}}</style>
</head><body>
<h2>打回成片审核</h2>
<p>Review ID: <code>{review_id}</code></p>
<form method="post" action="/api/review/{review_id}/reject-form?token={token}">
<label>打回原因（AI 将学习）</label><br>
<textarea name="reason" required placeholder="例如：开场不够痛、产品卖点不清晰"></textarea><br><br>
<button type="submit">提交打回</button>
</form>
<p><small>提示：此表单需配合 API 客户端；也可直接 POST JSON 到 /api/review/{{id}}/reject</small></p>
</body></html>"""
    return HTMLResponse(html)
