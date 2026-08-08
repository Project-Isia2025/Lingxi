"""投流报表回写 ROI 闭环。"""
from __future__ import annotations

import hashlib
from typing import Any

from core.storage import (
    get_ad_campaign_by_run,
    kb_boost_roi,
    kb_search,
    kb_upsert,
    metrics_record,
    update_ad_campaign_report,
)
from services.ad_traffic.client import get_campaign_report


def _synthetic_metrics(campaign_id: str) -> dict[str, Any]:
    h = int(hashlib.md5(campaign_id.encode()).hexdigest()[:8], 16)
    impressions = 800 + (h % 4200)
    clicks = max(1, int(impressions * (0.015 + (h % 30) / 1000)))
    cost = round(30 + (h % 170), 2)
    ctr = round(clicks / max(impressions, 1), 4)
    return {"impressions": impressions, "clicks": clicks, "cost_cny": cost, "ctr": ctr}


def fetch_ad_report(*, campaign_id: str, days: int = 7, dry_run: bool = False) -> dict[str, Any]:
    if dry_run or str(campaign_id).startswith("dry_"):
        return {"ok": True, "dry_run": True, "campaign_id": campaign_id, "metrics": _synthetic_metrics(campaign_id)}
    return get_campaign_report(campaign_id=campaign_id, days=days)


def compute_ad_roi_score(metrics: dict[str, Any]) -> float:
    impressions = float(metrics.get("impressions") or 0)
    clicks = float(metrics.get("clicks") or 0)
    cost = float(metrics.get("cost_cny") or metrics.get("cost") or 0)
    ctr = float(metrics.get("ctr") or (clicks / max(impressions, 1)))
    if impressions <= 0:
        return 0.0
    score = 0.0
    if ctr >= 0.02:
        score += 0.4
    elif ctr >= 0.01:
        score += 0.2
    if cost > 0 and clicks > 0:
        cpc = cost / clicks
        if cpc <= 2:
            score += 0.35
        elif cpc <= 5:
            score += 0.2
    if impressions >= 1000:
        score += 0.15
    return min(1.0, round(score, 3))


def sync_ad_report_for_run(run_id: str, *, days: int = 7) -> dict[str, Any]:
    """拉取投流报表 → 写入 metrics → 更新知识库 ROI。"""
    campaign = get_ad_campaign_by_run(run_id)
    if not campaign:
        return {"ok": False, "error": "no_campaign_for_run", "run_id": run_id}

    cid = str(campaign.get("campaign_id") or "")
    report = fetch_ad_report(campaign_id=cid, days=days, dry_run=bool(campaign.get("dry_run")))
    if not report.get("ok"):
        return report

    metrics = report.get("metrics") or {}
    ad_roi = compute_ad_roi_score(metrics)

    metrics_record(run_id=run_id, event_type="ad_impression", value=float(metrics.get("impressions") or 0), payload=metrics)
    metrics_record(run_id=run_id, event_type="ad_click", value=float(metrics.get("clicks") or 0), payload=metrics)
    metrics_record(run_id=run_id, event_type="ad_cost", value=float(metrics.get("cost_cny") or metrics.get("cost") or 0), payload=metrics)
    metrics_record(run_id=run_id, event_type="ad_roi", value=ad_roi, payload={"campaign_id": cid, **metrics})

    feedback = {
        "run_id": run_id,
        "campaign_id": cid,
        "metrics": metrics,
        "ad_roi_score": ad_roi,
        "recommendation": _ad_recommend(ad_roi, metrics),
    }
    update_ad_campaign_report(run_id, feedback)

    keyword = str(campaign.get("keyword") or "")
    if ad_roi >= 0.5 and keyword:
        kb_upsert(
            library="hotspot",
            title=f"投流表现佳：{keyword}",
            body=f"CTR={metrics.get('ctr')} 消耗={metrics.get('cost_cny')} 点击={metrics.get('clicks')}",
            tags=f"{keyword},ad_feedback",
            platform=str(campaign.get("platform") or "douyin"),
        )
        hits = kb_search(query=keyword, library="hotspot", limit=1)
        if hits:
            kb_boost_roi(item_id=int(hits[0]["id"]), delta=min(0.5, ad_roi * 0.3))

    try:
        from services.combined_roi import apply_combined_roi_for_run

        apply_combined_roi_for_run(run_id, keyword=keyword)
    except Exception:
        pass

    try:
        from services.roi_alert import dispatch_roi_alerts

        dispatch_roi_alerts(
            run_id=run_id,
            ad_roi=ad_roi,
            event="ad_report_sync",
            extra={"keyword": keyword, "campaign_id": cid},
        )
    except Exception:
        pass

    try:
        from services.dashboard_hub import notify_dashboard_update

        notify_dashboard_update(reason="ad_report_sync")
    except Exception:
        pass

    return {"ok": True, **feedback}


def sync_ad_report_and_bid(run_id: str, *, days: int = 7, apply_bid: bool = True) -> dict[str, Any]:
    """同步报表并运行自动调价。"""
    report = sync_ad_report_for_run(run_id, days=days)
    if not report.get("ok"):
        return report
    bid = None
    try:
        from services.ad_bid_engine import auto_bid_enabled, run_auto_bid_for_run

        if auto_bid_enabled():
            bid = run_auto_bid_for_run(run_id, apply=apply_bid)
            report["auto_bid"] = bid
    except Exception as exc:
        report["auto_bid_error"] = str(exc)
    return report


def _ad_recommend(ad_roi: float, metrics: dict[str, Any]) -> str:
    ctr = float(metrics.get("ctr") or 0)
    if ad_roi >= 0.6:
        return "投流表现优秀，建议加预算 15-20%"
    if ctr < 0.01:
        return "CTR 偏低，建议换钩子素材或缩窄人群"
    return "维持当前出价，24h 后再观察"


def apply_execution_ad_feedback(execution: dict[str, Any], *, run_id: str) -> dict[str, Any] | None:
    deploy = execution.get("ad_deploy") or {}
    cid = deploy.get("campaign_id") or ((deploy.get("api") or {}).get("create_result") or {}).get("campaign_id")
    if not cid and not get_ad_campaign_by_run(run_id):
        return None
    return sync_ad_report_for_run(run_id)
