"""联合 ROI 驱动投流自动调价。"""
from __future__ import annotations

import os
from typing import Any

from core.storage import get_ad_campaign_by_run, metrics_record
from services.ad_bid_engine import apply_bid_decision
from services.combined_roi import compute_combined_roi, resolve_run_roi_inputs


def combined_roi_bid_enabled() -> bool:
    return os.environ.get("COMBINED_ROI_BID_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def _pct(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def evaluate_combined_roi_bid(
    *,
    combined_roi_score: float,
    daily_budget_cny: float,
    publish_roi: float | None = None,
    ad_roi: float | None = None,
) -> dict[str, Any]:
    """根据联合 ROI 输出预算调整决策。"""
    scale_up = _pct("COMBINED_ROI_BID_SCALE", 0.72)
    scale_down = _pct("COMBINED_ROI_BID_CUT", 0.38)
    up_pct = _pct("COMBINED_ROI_BID_UP_PCT", 0.12)
    down_pct = _pct("COMBINED_ROI_BID_DOWN_PCT", 0.18)
    min_budget = _pct("COMBINED_ROI_BID_MIN_BUDGET", 30.0)
    max_budget = _pct("COMBINED_ROI_BID_MAX_BUDGET", 2000.0)

    action = "maintain"
    reason = "联合 ROI 平稳，维持预算"
    new_budget = daily_budget_cny

    if combined_roi_score >= scale_up:
        action = "increase_budget"
        boost = up_pct
        if publish_roi and ad_roi and publish_roi >= 0.65 and ad_roi >= 0.55:
            boost = up_pct * 1.25
        new_budget = round(daily_budget_cny * (1 + boost), 2)
        reason = f"联合 ROI {combined_roi_score:.2f} 优秀，加价 {boost:.0%}"
    elif combined_roi_score <= scale_down:
        action = "decrease_budget"
        new_budget = round(daily_budget_cny * (1 - down_pct), 2)
        reason = f"联合 ROI {combined_roi_score:.2f} 偏低，降价 {down_pct:.0%}"

    new_budget = max(min_budget, min(max_budget, new_budget))
    if action != "maintain" and abs(new_budget - daily_budget_cny) < 1:
        action = "maintain"
        reason = "预算调整幅度过小，维持不变"

    return {
        "action": action,
        "reason": reason,
        "rule_id": "combined_roi",
        "source": "combined_roi_bid",
        "combined_roi_score": combined_roi_score,
        "publish_roi": publish_roi,
        "ad_roi": ad_roi,
        "current_budget_cny": round(daily_budget_cny, 2),
        "new_budget_cny": round(new_budget, 2),
        "delta_cny": round(new_budget - daily_budget_cny, 2),
    }


def run_combined_roi_bid_for_run(run_id: str, *, apply: bool = True) -> dict[str, Any]:
    """联合 ROI → 投流预算调价。"""
    if not combined_roi_bid_enabled():
        return {"ok": False, "error": "combined_roi_bid_disabled"}

    campaign = get_ad_campaign_by_run(run_id)
    if not campaign:
        return {"ok": False, "error": "no_campaign_for_run", "run_id": run_id}

    pub, ad = resolve_run_roi_inputs(run_id)
    combined = compute_combined_roi(publish_roi=pub, ad_roi=ad)
    if not combined.get("ok"):
        return {"ok": False, "error": "no_combined_roi", "run_id": run_id, **combined}

    score = float(combined["combined_roi_score"])
    budget = float(campaign.get("daily_budget") or 100)
    decision = evaluate_combined_roi_bid(
        combined_roi_score=score,
        daily_budget_cny=budget,
        publish_roi=pub,
        ad_roi=ad,
    )

    result: dict[str, Any] = {"ok": True, "run_id": run_id, "combined": combined, "decision": decision}
    if apply and decision.get("action") != "maintain":
        result["apply"] = apply_bid_decision(run_id, decision, dry_run=bool(campaign.get("dry_run")))
        metrics_record(
            run_id=run_id,
            event_type="combined_roi_bid",
            value=score,
            payload={"decision": decision, "applied": result.get("apply")},
        )
    else:
        result["apply"] = {"ok": True, "applied": False, "action": "maintain"}
    return result
