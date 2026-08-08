"""成片审核队列。"""
from __future__ import annotations

import os
import uuid
from typing import Any

from core.storage import delete_review, enqueue_review, get_review_item, list_review_queue, update_review_status


def review_queue_enabled() -> bool:
    return os.environ.get("REVIEW_QUEUE_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def submit_for_review(
    *,
    run_id: str,
    video_path: str,
    script: str,
    title: str = "",
    payload: dict[str, Any] | None = None,
    notify_feishu: bool = True,
) -> dict[str, Any]:
    if not review_queue_enabled():
        return {"ok": False, "reason": "review_queue_disabled"}
    if not video_path:
        return {"ok": False, "reason": "missing_video_path"}

    review_id = f"rev-{uuid.uuid4().hex[:12]}"
    enqueue_review(
        review_id=review_id,
        run_id=run_id,
        video_path=video_path,
        script=script,
        title=title,
        payload=payload or {},
    )

    feishu_result = None
    if notify_feishu:
        from services.feishu_review import build_review_card, send_review_card

        card = build_review_card(
            review_id=review_id,
            run_id=run_id,
            title=title,
            video_path=video_path,
            script=script,
        )
        feishu_result = send_review_card(card)

    return {
        "ok": True,
        "review_id": review_id,
        "status": "pending_review",
        "feishu": feishu_result,
    }


def submit_batch_for_review(
    *,
    run_id: str,
    items: list[dict[str, Any]],
    notify_feishu: bool = True,
    feishu_batch_card: bool | None = None,
) -> dict[str, Any]:
    """批量提交多条成片到审核队列（如 3×15s 切片初稿）。"""
    if not review_queue_enabled():
        return {"ok": False, "reason": "review_queue_disabled"}
    if not items:
        return {"ok": False, "reason": "empty_items"}

    use_batch_card = feishu_batch_card if feishu_batch_card is not None else batch_card_enabled()
    submitted: list[dict[str, Any]] = []
    card_items: list[dict[str, Any]] = []

    for item in items:
        path = str(item.get("video_path") or "").strip()
        if not path:
            continue
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        review_id = f"rev-{uuid.uuid4().hex[:12]}"
        from services.tenant import attach_org

        merged_payload = attach_org(payload if isinstance(payload, dict) else {}, str(payload.get("org_id") or item.get("org_id") or ""))
        enqueue_review(
            review_id=review_id,
            run_id=run_id,
            video_path=path,
            script=str(item.get("script") or ""),
            title=str(item.get("title") or "")[:40],
            payload=merged_payload,
        )
        row = {
            "ok": True,
            "review_id": review_id,
            "status": "pending_review",
            "video_path": path,
            "script": str(item.get("script") or ""),
            "title": str(item.get("title") or "")[:40],
            "slice_id": payload.get("slice_id") or item.get("slice_id") or item.get("id"),
            "hook_style": payload.get("hook_style") or item.get("hook_style"),
        }
        submitted.append(row)
        card_items.append(row)

        if notify_feishu and not use_batch_card:
            from services.feishu_review import build_review_card, send_review_card

            card = build_review_card(
                review_id=review_id,
                run_id=run_id,
                title=row["title"],
                video_path=path,
                script=row["script"],
            )
            row["feishu"] = send_review_card(card)

    feishu_batch = None
    if notify_feishu and use_batch_card and card_items:
        from services.feishu_review import build_slice_batch_review_card, send_review_card

        first_payload = (items[0].get("payload") or {}) if items else {}
        card = build_slice_batch_review_card(
            run_id=run_id,
            title=str(card_items[0].get("title") or "").split("·")[0].strip(),
            items=card_items,
            keyword=str(first_payload.get("keyword") or ""),
            platform=str(first_payload.get("platform") or "douyin"),
        )
        feishu_batch = send_review_card(card)

    ok = [s for s in submitted if s.get("ok")]
    return {
        "ok": bool(ok),
        "count": len(ok),
        "submitted": submitted,
        "review_ids": [s.get("review_id") for s in ok if s.get("review_id")],
        "feishu_batch": feishu_batch,
        "batch_card": use_batch_card,
    }


def batch_card_enabled() -> bool:
    from services.feishu_review import batch_card_enabled as _b

    return _b()


def approve_review(*, review_id: str, token: str = "") -> dict[str, Any]:
    from services.feishu_review import verify_review_token

    item = get_review_item(review_id)
    if not item:
        return {"ok": False, "error": "review_not_found"}
    if not token:
        return {"ok": False, "error": "token_required"}
    if not verify_review_token(review_id, token):
        return {"ok": False, "error": "invalid_token"}
    if item.get("status") != "pending_review":
        return {"ok": False, "error": "already_reviewed", "status": item.get("status")}

    update_review_status(review_id=review_id, status="approved")
    payload = dict(item.get("payload") or {})
    publish_result = None
    slice_publish = None

    if payload.get("batch") == "slice_drafts":
        try:
            from services.slice_publish import publish_approved_slice

            slice_publish = publish_approved_slice(item)
            publish_result = slice_publish.get("publish")
        except Exception as exc:
            slice_publish = {"ok": False, "error": str(exc)[:200]}
    elif bool(payload.get("auto_publish_on_approve", True)):
        try:
            from services.publish.scheduler import schedule_publish

            publish_result = schedule_publish(
                platform=str(payload.get("platform") or "douyin"),
                video_path=str(item.get("video_path") or ""),
                script=str(item.get("script") or ""),
                title=str(item.get("title") or ""),
                run_id=str(item.get("run_id") or ""),
                account_id=str(payload.get("account_id") or "default"),
            )
        except Exception as exc:
            publish_result = {"ok": False, "error": str(exc)}

    _maybe_auto_delete_review(review_id)
    return {
        "ok": True,
        "review_id": review_id,
        "status": "approved",
        "publish": publish_result,
        "slice_publish": slice_publish,
    }


def reject_review(*, review_id: str, reason: str, token: str = "") -> dict[str, Any]:
    from services.feishu_review import verify_review_token
    from services.review_learning import learn_from_rejection

    item = get_review_item(review_id)
    if not item:
        return {"ok": False, "error": "review_not_found"}
    if not token:
        return {"ok": False, "error": "token_required"}
    if not verify_review_token(review_id, token):
        return {"ok": False, "error": "invalid_token"}
    if item.get("status") != "pending_review":
        return {"ok": False, "error": "already_reviewed", "status": item.get("status")}

    update_review_status(review_id=review_id, status="rejected", reject_reason=reason)
    payload = dict(item.get("payload") or {})
    learn = learn_from_rejection(
        run_id=str(item.get("run_id") or ""),
        review_id=review_id,
        reason=reason,
        script=str(item.get("script") or ""),
        keyword=str(payload.get("keyword") or ""),
        platform=str(payload.get("platform") or "douyin"),
    )
    _maybe_auto_delete_review(review_id)
    return {"ok": True, "review_id": review_id, "status": "rejected", "learning": learn}


def _maybe_auto_delete_review(review_id: str) -> None:
    try:
        from services.task_cleanup import review_auto_delete_on_resolve

        if review_auto_delete_on_resolve():
            delete_review(review_id)
    except Exception:
        pass


def delete_review_item(review_id: str) -> dict[str, Any]:
    from services.task_cleanup import delete_review_item as _delete

    return _delete(review_id, allow_pending=True)


def get_review_status(*, limit: int = 20) -> dict[str, Any]:
    pending = list_review_queue(status="pending_review", limit=limit)
    return {
        "ok": True,
        "enabled": review_queue_enabled(),
        "pending_count": len(pending),
        "pending": pending,
    }
