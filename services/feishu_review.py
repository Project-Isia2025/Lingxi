"""飞书审核卡片。"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

import requests


def review_enabled() -> bool:
    return os.environ.get("REVIEW_QUEUE_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def webhook_url(org_id: str = "") -> str:
    try:
        from services.org_webhook_config import resolve_webhook

        org_url = resolve_webhook(org_id, "review")
        if org_url:
            return org_url
    except Exception:
        pass
    return (os.environ.get("REVIEW_FEISHU_WEBHOOK_URL") or os.environ.get("ROI_ALERT_WEBHOOK_URL") or "").strip()


def review_base_url(org_id: str = "") -> str:
    try:
        from services.org_webhook_config import resolve_review_base_url

        return resolve_review_base_url(org_id)
    except Exception:
        pass
    return (os.environ.get("REVIEW_BASE_URL") or "http://127.0.0.1:9200").rstrip("/")


def review_token(review_id: str) -> str:
    secret = (os.environ.get("REVIEW_TOKEN_SECRET") or "matrix-review-dev").encode("utf-8")
    return hmac.new(secret, review_id.encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def verify_review_token(review_id: str, token: str) -> bool:
    if not token:
        return False
    return hmac.compare_digest(review_token(review_id), token)


def verify_batch_review_token(run_id: str, token: str) -> bool:
    if not token or not run_id:
        return False
    secret = (os.environ.get("REVIEW_TOKEN_SECRET") or "matrix-review-dev").encode("utf-8")
    expected = hmac.new(secret, f"batch-{run_id}".encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    return hmac.compare_digest(token, expected)


def use_callback_buttons() -> bool:
    return os.environ.get("REVIEW_FEISHU_USE_CALLBACK", "1").strip().lower() in ("1", "true", "yes", "on")


def batch_card_enabled() -> bool:
    return os.environ.get("REVIEW_FEISHU_BATCH_CARD", "1").strip().lower() not in ("0", "false", "no", "off")


def _callback_value(*, action: str, review_id: str, token: str, slice_id: str = "") -> dict[str, str]:
    val: dict[str, str] = {"action": action, "review_id": review_id, "token": token}
    if slice_id:
        val["slice_id"] = slice_id
    return val


def _review_actions(*, review_id: str, token: str, slice_id: str = "") -> list[dict[str, Any]]:
    base = review_base_url()
    if use_callback_buttons():
        return [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "确认发布"},
                "type": "primary",
                "value": _callback_value(action="approve", review_id=review_id, token=token, slice_id=slice_id),
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "打回修改"},
                "type": "danger",
                "value": _callback_value(action="reject", review_id=review_id, token=token, slice_id=slice_id),
            },
        ]
    approve_url = f"{base}/api/review/{review_id}/approve?token={token}"
    reject_url = f"{base}/dashboard/review?review_id={review_id}&token={token}"
    return [
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "确认发布"},
            "url": approve_url,
            "type": "primary",
        },
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "打回修改"},
            "url": reject_url,
            "type": "danger",
        },
    ]


def build_review_card(*, review_id: str, run_id: str, title: str, video_path: str, script: str) -> dict[str, Any]:
    tok = review_token(review_id)
    preview = (script or "")[:180].replace("\n", " ")
    actions = _review_actions(review_id=review_id, token=tok)

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "矩阵 Agent 成片审核"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**Run:** `{run_id}`\n"
                            f"**标题:** {title or '未命名'}\n"
                            f"**成片:** `{video_path}`\n"
                            f"**脚本摘要:** {preview or '-'}"
                        ),
                    },
                },
                {"tag": "action", "actions": actions},
            ],
        },
    }


def build_slice_batch_review_card(
    *,
    run_id: str,
    title: str,
    items: list[dict[str, Any]],
    keyword: str = "",
    platform: str = "",
) -> dict[str, Any]:
    """3×15s 切片合并审核卡片：每条切片独立确认/打回按钮。"""
    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**Run:** `{run_id}`\n"
                    f"**Campaign:** {title or '未命名'}\n"
                    f"**关键词:** {keyword or '-'} | **平台:** {platform or 'douyin'}\n"
                    f"**待审切片:** {len(items)} 条（15秒独立初稿）"
                ),
            },
        },
        {"tag": "hr"},
    ]

    for idx, item in enumerate(items, 1):
        review_id = str(item.get("review_id") or "")
        slice_id = str(item.get("slice_id") or item.get("id") or f"S{idx}")
        hook = str(item.get("hook_style") or "")
        script = str(item.get("script") or "")
        video_path = str(item.get("video_path") or "")
        preview = script[:120].replace("\n", " ")
        tok = review_token(review_id) if review_id else ""

        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**切片 {slice_id}** · {hook or '痛点+解决方案'}\n"
                    f"**脚本:** {preview or '-'}\n"
                    f"**成片:** `{video_path}`"
                ),
            },
        })
        if review_id:
            elements.append({"tag": "action", "actions": _review_actions(review_id=review_id, token=tok, slice_id=slice_id)})
        if idx < len(items):
            elements.append({"tag": "hr"})

    batch_token = review_token(f"batch-{run_id}") if run_id else ""
    if use_callback_buttons() and len(items) >= 2 and batch_token:
        elements.append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "全部确认发布"},
                    "type": "primary",
                    "value": {
                        "action": "approve_all_slices",
                        "run_id": run_id,
                        "token": batch_token,
                    },
                },
            ],
        })

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"矩阵 Agent · {len(items)} 条切片审核"},
                "template": "wathet",
            },
            "elements": elements,
        },
    }


def parse_callback_body(body: dict[str, Any]) -> dict[str, Any]:
    """解析飞书卡片回调或通用 JSON。"""
    if not isinstance(body, dict):
        return {"ok": False, "error": "invalid_body"}

    if "challenge" in body:
        return {"ok": True, "type": "url_verification", "challenge": body["challenge"]}

    action_block = body.get("action") or {}
    value = action_block.get("value") if isinstance(action_block, dict) else None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = {"action": value}
    if not isinstance(value, dict):
        value = {}

    review_id = str(
        value.get("review_id")
        or body.get("review_id")
        or action_block.get("review_id")
        or ""
    ).strip()
    act = str(
        value.get("action")
        or body.get("action")
        or action_block.get("tag")
        or ""
    ).strip().lower()
    token = str(value.get("token") or body.get("token") or "").strip()
    reason = str(
        value.get("reason")
        or body.get("reason")
        or body.get("reject_reason")
        or ""
    ).strip()

    if body.get("type") == "card.action.trigger" and not act and value:
        act = str(value.get("action") or "").strip().lower()

    if act in ("reject", "打回", "打回修改"):
        act = "reject"
    elif act in ("approve", "确认", "确认发布"):
        act = "approve"

    if not review_id or not act:
        if act == "approve_all_slices" and (value.get("run_id") or body.get("run_id")):
            run_id = str(value.get("run_id") or body.get("run_id") or "").strip()
            token = str(value.get("token") or body.get("token") or "").strip()
            return {
                "ok": True,
                "type": "approve_all_slices",
                "run_id": run_id,
                "token": token,
            }
        return {"ok": False, "error": "missing_review_id_or_action", "parsed": {"review_id": review_id, "action": act}}

    if act == "approve_all_slices":
        run_id = str(value.get("run_id") or body.get("run_id") or review_id or "").strip()
        token = str(value.get("token") or body.get("token") or "").strip()
        return {
            "ok": True,
            "type": "approve_all_slices",
            "run_id": run_id,
            "token": token,
        }

    return {
        "ok": True,
        "type": "review_action",
        "review_id": review_id,
        "action": act,
        "token": token,
        "reason": reason,
    }


def handle_review_callback(body: dict[str, Any]) -> dict[str, Any]:
    """统一处理飞书/通用审核回调。"""
    parsed = parse_callback_body(body)
    if not parsed.get("ok"):
        return parsed

    if parsed.get("type") == "url_verification":
        return {"challenge": parsed["challenge"]}

    if parsed.get("type") == "approve_all_slices":
        from services.slice_publish import approve_all_pending_slices

        run_id = str(parsed.get("run_id") or "")
        token = str(parsed.get("token") or "")
        if not token:
            return {"toast": {"type": "error", "content": "缺少 batch token"}, "ok": False}
        if not verify_batch_review_token(run_id, token):
            return {"toast": {"type": "error", "content": "批量确认 token 无效"}, "ok": False}
        result = approve_all_pending_slices(run_id=run_id, token=token)
        if result.get("ok"):
            return {
                "toast": {
                    "type": "success",
                    "content": f"已确认 {result.get('approved')}/{result.get('total')} 条切片并进入发布/矩阵队列",
                },
                "result": result,
            }
        return {
            "toast": {"type": "error", "content": str(result.get("error") or "批量确认失败")},
            "result": result,
        }

    from services.review_queue import approve_review, reject_review

    review_id = parsed["review_id"]
    token = parsed.get("token") or ""
    act = parsed["action"]

    if act == "approve":
        result = approve_review(review_id=review_id, token=token)
        if result.get("ok"):
            msg = "已确认，切片已进入发布/矩阵队列" if (result.get("slice_publish") or {}).get("matrix") else "已确认，成片已进入发布队列"
            return {
                "toast": {"type": "success", "content": msg},
                "result": result,
            }
        return {"toast": {"type": "error", "content": str(result.get("error") or "审核失败")}, "result": result}

    if act == "reject":
        reason = parsed.get("reason") or "飞书卡片打回（未填写原因）"
        result = reject_review(review_id=review_id, reason=reason, token=token)
        if result.get("ok"):
            return {
                "toast": {"type": "info", "content": "已打回，原因已写入知识库"},
                "result": result,
            }
        return {"toast": {"type": "error", "content": str(result.get("error") or "打回失败")}, "result": result}

    return {"ok": False, "error": "unknown_action", "action": act}


def send_review_card(payload: dict[str, Any]) -> dict[str, Any]:
    org_id = str(payload.get("org_id") or (payload.get("card") or {}).get("org_id") or "")
    url = webhook_url(org_id)
    if not url:
        return {"ok": False, "reason": "feishu_webhook_not_configured"}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            data=body,
            timeout=int(os.environ.get("REVIEW_WEBHOOK_TIMEOUT_SEC", "15")),
        )
        ok = 200 <= resp.status_code < 300
        return {"ok": ok, "status_code": resp.status_code, "response": resp.text[:500]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}
