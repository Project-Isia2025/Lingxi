"""飞书审核配置就绪状态。"""
from __future__ import annotations

import os
from typing import Any

from services.feishu_review import (
    batch_card_enabled,
    review_base_url,
    review_enabled,
    use_callback_buttons,
    webhook_url,
)


def feishu_review_status(org_id: str = "") -> dict[str, Any]:
    from services.org_webhook_config import resolve_review_base_url, resolve_webhook

    oid = (org_id or "").strip()
    url = resolve_webhook(oid, "review") if oid else webhook_url()
    if oid:
        base = resolve_review_base_url(oid)
    else:
        base = review_base_url()
    callback_url = f"{base}/api/review/callback"
    return {
        "ok": True,
        "org_id": oid or "(default)",
        "review_enabled": review_enabled(),
        "webhook_configured": bool(url),
        "webhook_preview": (url[:32] + "...") if len(url) > 32 else url,
        "callback_url": callback_url,
        "callback_buttons": use_callback_buttons(),
        "batch_card": batch_card_enabled(),
        "base_url": base,
        "token_secret_set": bool((os.environ.get("REVIEW_TOKEN_SECRET") or "").strip()),
        "live_ready": bool(url and base),
        "setup_hint": (
            "配置 REVIEW_FEISHU_WEBHOOK_URL + REVIEW_BASE_URL（公网可达）并在飞书机器人启用卡片回调"
            if not url
            else "Webhook 已配置，请确保飞书回调 URL 指向 /api/review/callback"
        ),
    }
