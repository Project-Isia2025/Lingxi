"""飞书 / 企业微信 Webhook 消息格式适配。"""
from __future__ import annotations

import json
import os
from typing import Any


def webhook_provider() -> str:
    """auto | feishu | wecom | generic"""
    raw = (os.environ.get("ROI_ALERT_WEBHOOK_PROVIDER") or "auto").strip().lower()
    return raw or "auto"


def detect_provider(url: str) -> str:
    u = (url or "").lower()
    if "open.feishu.cn" in u or "open.larksuite.com" in u:
        return "feishu"
    if "qyapi.weixin.qq.com" in u:
        return "wecom"
    return "generic"


def _level_emoji(level: str) -> str:
    return {"info": "✅", "warning": "⚠️", "error": "❌"}.get(level, "ℹ️")


def format_alert_text(payload: dict[str, Any]) -> str:
    alerts = payload.get("alerts") or []
    lines = [
        f"【矩阵 Agent ROI 告警】",
        f"事件: {payload.get('event') or 'roi_alert'}",
        f"Run: {payload.get('run_id') or '-'}",
    ]
    if payload.get("combined_roi") is not None:
        lines.append(f"联合 ROI: {payload['combined_roi']}")
    if payload.get("publish_roi") is not None:
        lines.append(f"发布 ROI: {payload['publish_roi']}")
    if payload.get("ad_roi") is not None:
        lines.append(f"投流 ROI: {payload['ad_roi']}")
    extra = payload.get("extra") or {}
    if extra.get("keyword"):
        lines.append(f"关键词: {extra['keyword']}")
    if extra.get("platform"):
        lines.append(f"平台: {extra['platform']}")
    if extra.get("error"):
        lines.append(f"错误: {extra['error']}")
    lines.append("---")
    for a in alerts:
        lines.append(f"{_level_emoji(str(a.get('level') or ''))} {a.get('message') or a.get('type')}")
    return "\n".join(lines)


def format_feishu_payload(payload: dict[str, Any]) -> dict[str, Any]:
    text = format_alert_text(payload)
    return {"msg_type": "text", "content": {"text": text}}


def format_wecom_payload(payload: dict[str, Any]) -> dict[str, Any]:
    text = format_alert_text(payload)
    return {"msgtype": "text", "text": {"content": text}}


def format_webhook_body(payload: dict[str, Any], *, url: str = "") -> dict[str, Any]:
    provider = webhook_provider()
    if provider == "auto":
        provider = detect_provider(url)
    if provider == "feishu":
        return format_feishu_payload(payload)
    if provider == "wecom":
        return format_wecom_payload(payload)
    return {
        "source": "matrix_agent",
        "event": payload.get("event") or "roi_alert",
        **payload,
    }


def format_webhook_bytes(payload: dict[str, Any], *, url: str = "") -> bytes:
    body = format_webhook_body(payload, url=url)
    return json.dumps(body, ensure_ascii=False).encode("utf-8")
