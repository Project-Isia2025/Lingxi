"""ROI 告警 Webhook。"""
from __future__ import annotations

import os
from typing import Any

import requests

from services.roi_alert_dedup import filter_deduped_alerts
from services.roi_alert_format import format_webhook_bytes, webhook_provider


def roi_alert_enabled() -> bool:
    return os.environ.get("ROI_ALERT_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def webhook_url() -> str:
    return (os.environ.get("ROI_ALERT_WEBHOOK_URL") or os.environ.get("WEBHOOK_URL") or "").strip()


def _threshold(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def evaluate_roi_alerts(
    *,
    run_id: str,
    combined_roi: float | None = None,
    publish_roi: float | None = None,
    ad_roi: float | None = None,
    event: str = "combined_roi",
) -> list[dict[str, Any]]:
    """评估 ROI 是否触发告警。"""
    alerts: list[dict[str, Any]] = []
    high = _threshold("ROI_ALERT_COMBINED_HIGH", 0.75)
    low = _threshold("ROI_ALERT_COMBINED_LOW", 0.35)

    if combined_roi is not None:
        if combined_roi >= high:
            alerts.append({
                "level": "info",
                "type": "combined_roi_high",
                "message": f"联合 ROI {combined_roi:.2f} 达到优秀线 {high}",
                "run_id": run_id,
                "value": combined_roi,
            })
        elif combined_roi <= low:
            alerts.append({
                "level": "warning",
                "type": "combined_roi_low",
                "message": f"联合 ROI {combined_roi:.2f} 低于警戒线 {low}",
                "run_id": run_id,
                "value": combined_roi,
            })

    if publish_roi is not None and publish_roi <= _threshold("ROI_ALERT_PUBLISH_LOW", 0.4):
        alerts.append({
            "level": "warning",
            "type": "publish_roi_low",
            "message": f"发布 ROI {publish_roi:.2f} 偏低",
            "run_id": run_id,
            "value": publish_roi,
        })

    if ad_roi is not None and ad_roi <= _threshold("ROI_ALERT_AD_LOW", 0.35):
        alerts.append({
            "level": "warning",
            "type": "ad_roi_low",
            "message": f"投流 ROI {ad_roi:.2f} 偏低",
            "run_id": run_id,
            "value": ad_roi,
        })

    if event == "publish_fail":
        alerts.append({
            "level": "error",
            "type": "publish_failed",
            "message": "发布失败",
            "run_id": run_id,
        })

    return alerts


def _validate_webhook_response(*, ok: bool, provider: str, url: str, resp: requests.Response) -> bool:
    """校验飞书 code / 企微 errcode 等业务层成功标志。"""
    if not ok:
        return False
    resolved = provider
    if resolved == "auto":
        from services.roi_alert_format import detect_provider

        resolved = detect_provider(url)
    try:
        data = resp.json()
    except Exception:
        return ok
    if resolved == "feishu" and "code" in data:
        return int(data.get("code", 0)) == 0
    if resolved == "wecom" and "errcode" in data:
        return int(data.get("errcode", 0)) == 0
    return ok


def send_roi_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """POST 告警到 Webhook（飞书/企业微信/自定义 JSON）。"""
    if not roi_alert_enabled():
        return {"ok": False, "reason": "roi_alert_disabled"}
    url = webhook_url()
    if not url:
        return {"ok": False, "reason": "webhook_url_not_configured"}

    provider = webhook_provider()
    body_bytes = format_webhook_bytes(payload, url=url)
    try:
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            data=body_bytes,
            timeout=int(os.environ.get("ROI_ALERT_TIMEOUT_SEC", "15")),
        )
        http_ok = 200 <= resp.status_code < 300
        ok = _validate_webhook_response(ok=http_ok, provider=provider, url=url, resp=resp)
        return {
            "ok": ok,
            "provider": provider,
            "status_code": resp.status_code,
            "response": resp.text[:500],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


def dispatch_roi_alerts(
    *,
    run_id: str,
    combined_roi: float | None = None,
    publish_roi: float | None = None,
    ad_roi: float | None = None,
    event: str = "combined_roi",
    extra: dict[str, Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """评估、去重并发送 ROI 告警。"""
    alerts = evaluate_roi_alerts(
        run_id=run_id,
        combined_roi=combined_roi,
        publish_roi=publish_roi,
        ad_roi=ad_roi,
        event=event,
    )
    if not alerts:
        return {"ok": True, "alerts": [], "sent": False}

    skipped: list[str] = []
    if not force:
        alerts, skipped = filter_deduped_alerts(run_id=run_id, alerts=alerts, event=event)
    if not alerts:
        return {"ok": True, "alerts": [], "sent": False, "deduped": True, "skipped_keys": skipped}

    result = send_roi_webhook({
        "run_id": run_id,
        "event": event,
        "alerts": alerts,
        "combined_roi": combined_roi,
        "publish_roi": publish_roi,
        "ad_roi": ad_roi,
        "extra": extra or {},
    })
    try:
        from core.storage import metrics_record

        metrics_record(
            run_id=run_id,
            event_type="roi_alert",
            value=float(combined_roi or publish_roi or ad_roi or 0),
            payload={"alerts": alerts, "webhook": result, "skipped_keys": skipped},
        )
    except Exception:
        pass
    return {
        "ok": True,
        "alerts": alerts,
        "webhook": result,
        "sent": result.get("ok"),
        "deduped": bool(skipped),
        "skipped_keys": skipped,
    }
