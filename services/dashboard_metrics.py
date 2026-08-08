"""Dashboard 指标图表数据。"""
from __future__ import annotations

from typing import Any


def build_metrics_chart(*, days: int = 14) -> dict[str, Any]:
    from core.storage import metrics_daily_series, metrics_summary

    roi_types = ("publish_roi", "ad_roi", "combined_roi")
    series = metrics_daily_series(days=days, event_types=roi_types)
    summary = metrics_summary(days=days)
    by_event = summary.get("by_event") or {}

    latest_scores = {
        "publish_roi": _avg_recent(series, "publish_roi"),
        "ad_roi": _avg_recent(series, "ad_roi"),
        "combined_roi": _avg_recent(series, "combined_roi"),
    }
    publish_count = int((by_event.get("publish_ok") or {}).get("count") or 0)
    ad_bid_count = int((by_event.get("ad_bid_adjust") or {}).get("count") or 0)
    combined_bid_count = int((by_event.get("combined_roi_bid") or {}).get("count") or 0)

    return {
        "ok": True,
        "days": days,
        "series": series,
        "latest_avg": latest_scores,
        "totals": {
            "publish_ok": publish_count,
            "ad_bid_adjust": ad_bid_count,
            "combined_roi_bid": combined_bid_count,
        },
    }


def _avg_recent(series: list[dict[str, Any]], event_type: str) -> float | None:
    rows = [r for r in series if r.get("event_type") == event_type and r.get("avg_value") is not None]
    if not rows:
        return None
    vals = [float(r["avg_value"]) for r in rows[-7:]]
    return round(sum(vals) / len(vals), 3) if vals else None
