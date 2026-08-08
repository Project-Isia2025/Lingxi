"""ROI 指标 CSV 导出。"""
from __future__ import annotations

import csv
import io
import os
from typing import Any

from core.storage import metrics_daily_series, metrics_export_rows


def export_roi_csv(*, days: int = 30) -> str:
    """导出 ROI 相关 metrics 为 CSV 文本。"""
    days = max(1, min(days, 90))
    event_types = ("publish_roi", "ad_roi", "combined_roi", "publish_ok", "combined_roi_bid", "ad_bid_adjust")
    rows = metrics_export_rows(days=days, event_types=event_types)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["run_id", "event_type", "metric_value", "created_at", "platform", "payload_summary"])
    for row in rows:
        payload = row.get("payload") or {}
        summary = _payload_summary(payload)
        writer.writerow([
            row.get("run_id") or "",
            row.get("event_type") or "",
            row.get("metric_value") or "",
            row.get("created_at") or "",
            payload.get("platform") or "",
            summary,
        ])

    daily = metrics_daily_series(days=days, event_types=("publish_roi", "ad_roi", "combined_roi"))
    writer.writerow([])
    writer.writerow(["# daily_aggregate"])
    writer.writerow(["day", "event_type", "count", "avg_value", "sum_value"])
    for d in daily:
        writer.writerow([
            d.get("day") or "",
            d.get("event_type") or "",
            d.get("cnt") or "",
            d.get("avg_value") or "",
            d.get("sum_value") or "",
        ])
    return buf.getvalue()


def _payload_summary(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    keys = ("publish_roi_score", "ad_roi_score", "combined_roi_score", "post_url", "action", "recommendation")
    parts = []
    for k in keys:
        if k in payload and payload[k] not in (None, ""):
            parts.append(f"{k}={payload[k]}")
    return "; ".join(parts)[:500]


def roi_export_enabled() -> bool:
    return os.environ.get("ROI_EXPORT_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")
