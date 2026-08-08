"""切片审核通过后：发布队列 + 矩阵分发 + 完播监控。"""
from __future__ import annotations

import os
from typing import Any


def slice_matrix_on_approve_enabled() -> bool:
    return os.environ.get("SLICE_APPROVE_MATRIX_PUBLISH", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def slice_monitor_on_approve_enabled() -> bool:
    return os.environ.get("SLICE_APPROVE_MONITOR", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def list_slice_reviews_for_run(*, run_id: str, status: str = "") -> list[dict[str, Any]]:
    from core.storage import list_review_queue

    items = list_review_queue(status=status, limit=100)
    out = []
    for item in items:
        if str(item.get("run_id") or "") != run_id:
            continue
        payload = dict(item.get("payload") or {})
        if payload.get("batch") != "slice_drafts":
            continue
        out.append(item)
    out.sort(key=lambda x: str((x.get("payload") or {}).get("slice_id") or x.get("review_id") or ""))
    return out


def publish_approved_slice(item: dict[str, Any]) -> dict[str, Any]:
    """单条切片审核通过后：入发布队列，可选矩阵分发与完播监控。"""
    payload = dict(item.get("payload") or {})
    run_id = str(item.get("run_id") or "")
    platform = str(payload.get("platform") or "douyin")
    org_id = str(payload.get("org_id") or "")
    video_path = str(item.get("video_path") or "")
    script = str(item.get("script") or "")
    title = str(item.get("title") or "")
    slice_id = str(payload.get("slice_id") or "")

    if not video_path:
        return {"ok": False, "error": "missing_video_path", "slice_id": slice_id}

    publish_result = None
    matrix_result = None
    monitor_result = None

    if bool(payload.get("auto_publish_on_approve", True)):
        try:
            from services.publish.scheduler import schedule_publish

            publish_result = schedule_publish(
                platform=platform,
                video_path=video_path,
                script=script,
                title=title,
                run_id=run_id,
                account_id=str(payload.get("account_id") or "default"),
                org_id=org_id,
            )
        except Exception as exc:
            publish_result = {"ok": False, "error": str(exc)[:200]}

    if slice_matrix_on_approve_enabled() and payload.get("batch") == "slice_drafts":
        try:
            from services.matrix_strategy import auto_matrix_publish

            plats = payload.get("matrix_platforms")
            if isinstance(plats, str):
                plats = [p.strip() for p in plats.split(",") if p.strip()]
            matrix_result = auto_matrix_publish(
                run_id=run_id or f"slice-{slice_id}",
                video_path=video_path,
                script=script,
                title=title,
                platforms=plats if isinstance(plats, list) and plats else None,
                org_id=org_id,
            )
        except Exception as exc:
            matrix_result = {"ok": False, "error": str(exc)[:200]}

    if slice_monitor_on_approve_enabled():
        try:
            from services.post_publish_monitor import schedule_monitor

            monitor_result = schedule_monitor(
                run_id=run_id or f"slice-{slice_id}",
                platform=platform,
                post_url=str(payload.get("post_url") or publish_result.get("post_url") if isinstance(publish_result, dict) else ""),
                job_id=str((publish_result or {}).get("job_id") or ""),
                keyword=str(payload.get("keyword") or ""),
                script=script,
            )
        except Exception as exc:
            monitor_result = {"ok": False, "error": str(exc)[:200]}

    ok = bool((publish_result or {}).get("ok")) or bool((matrix_result or {}).get("ok"))
    return {
        "ok": ok,
        "slice_id": slice_id,
        "review_id": item.get("review_id"),
        "publish": publish_result,
        "matrix": matrix_result,
        "monitor": monitor_result,
    }


def approve_all_pending_slices(*, run_id: str, token: str = "") -> dict[str, Any]:
    """批量确认同一 run 下所有待审切片。"""
    from services.feishu_review import review_token, verify_batch_review_token, verify_review_token
    from services.review_queue import approve_review

    pending = list_slice_reviews_for_run(run_id=run_id, status="pending_review")
    if not pending:
        return {"ok": False, "error": "no_pending_slices", "run_id": run_id}

    batch_ok = verify_batch_review_token(run_id, token)
    results = []
    for item in pending:
        rid = str(item.get("review_id") or "")
        if batch_ok:
            tok = review_token(rid)
        elif token and verify_review_token(rid, token):
            tok = token
        else:
            err = "invalid_token" if token else "token_required"
            results.append({"ok": False, "review_id": rid, "error": err})
            continue
        results.append(approve_review(review_id=rid, token=tok))

    ok = [r for r in results if r.get("ok")]
    return {
        "ok": bool(ok),
        "run_id": run_id,
        "approved": len(ok),
        "total": len(pending),
        "results": results,
    }


def slice_batch_status(*, run_id: str) -> dict[str, Any]:
    pending = list_slice_reviews_for_run(run_id=run_id, status="pending_review")
    approved = list_slice_reviews_for_run(run_id=run_id, status="approved")
    rejected = list_slice_reviews_for_run(run_id=run_id, status="rejected")
    return {
        "ok": True,
        "run_id": run_id,
        "pending": len(pending),
        "approved": len(approved),
        "rejected": len(rejected),
        "items": {
            "pending": [
                {
                    "review_id": i.get("review_id"),
                    "slice_id": (i.get("payload") or {}).get("slice_id"),
                    "title": i.get("title"),
                }
                for i in pending
            ],
            "approved": [
                {
                    "review_id": i.get("review_id"),
                    "slice_id": (i.get("payload") or {}).get("slice_id"),
                }
                for i in approved
            ],
        },
    }
