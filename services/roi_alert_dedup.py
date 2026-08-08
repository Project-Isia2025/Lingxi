"""ROI 告警去重（防刷屏）。"""
from __future__ import annotations

import os
import time
from typing import Any


def dedup_enabled() -> bool:
    return os.environ.get("ROI_ALERT_DEDUP_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def dedup_ttl_sec() -> int:
    try:
        return max(60, int(os.environ.get("ROI_ALERT_DEDUP_SEC", "3600")))
    except ValueError:
        return 3600


def build_dedupe_key(*, run_id: str, alert: dict[str, Any], event: str) -> str:
    atype = str(alert.get("type") or "unknown")
    val = alert.get("value")
    val_bucket = ""
    if isinstance(val, (int, float)):
        val_bucket = f":{int(float(val) * 100)}"
    return f"{event}:{run_id}:{atype}{val_bucket}"


def filter_deduped_alerts(
    *,
    run_id: str,
    alerts: list[dict[str, Any]],
    event: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """返回未去重拦截的告警列表。"""
    if not dedup_enabled() or not alerts:
        return alerts, []

    from core.storage import alert_was_sent_recently, record_alert_sent

    passed: list[dict[str, Any]] = []
    skipped: list[str] = []
    ttl = dedup_ttl_sec()
    now = int(time.time())

    for alert in alerts:
        key = build_dedupe_key(run_id=run_id, alert=alert, event=event)
        if alert_was_sent_recently(key, within_sec=ttl):
            skipped.append(key)
            continue
        passed.append(alert)
        record_alert_sent(dedupe_key=key, run_id=run_id, alert_type=str(alert.get("type") or ""), sent_ts=now)

    return passed, skipped
