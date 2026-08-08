"""投流自动调价规则引擎。"""
from __future__ import annotations

import os
from typing import Any

from core.storage import get_ad_campaign_by_run, metrics_record
from services.ad_bid_config import apply_rules_to_env, load_bid_rules
from services.ad_traffic.client import update_campaign_budget


def auto_bid_enabled() -> bool:
    rules = load_bid_rules()
    apply_rules_to_env(rules)
    if "enabled" in rules:
        return bool(rules["enabled"])
    return os.environ.get("AD_AUTO_BID_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def _rule_enabled(rules: dict[str, Any], rule_id: str) -> bool:
    for row in rules.get("rules") or []:
        if isinstance(row, dict) and str(row.get("id")) == rule_id:
            return bool(row.get("enabled", True))
    return True


def _pct_from_rules(rules: dict[str, Any], key: str, env_name: str, default: float) -> float:
    if key in rules:
        try:
            return float(rules[key])
        except (TypeError, ValueError):
            pass
    try:
        return float(os.environ.get(env_name, str(default)))
    except ValueError:
        return default


def evaluate_bid_rules(
    *,
    metrics: dict[str, Any],
    ad_roi_score: float,
    daily_budget_cny: float,
) -> dict[str, Any]:
    """根据报表指标输出调价决策（读取 JSON 规则配置）。"""
    rules = load_bid_rules()
    apply_rules_to_env(rules)

    impressions = float(metrics.get("impressions") or 0)
    clicks = float(metrics.get("clicks") or 0)
    cost = float(metrics.get("cost_cny") or metrics.get("cost") or 0)
    ctr = float(metrics.get("ctr") or (clicks / max(impressions, 1)))
    cpc = cost / max(clicks, 1) if clicks > 0 else 999.0

    ctr_good = _pct_from_rules(rules, "ctr_good", "AD_BID_CTR_GOOD", 0.02)
    ctr_bad = _pct_from_rules(rules, "ctr_bad", "AD_BID_CTR_BAD", 0.008)
    cpc_max = _pct_from_rules(rules, "cpc_max", "AD_BID_CPC_MAX", 8.0)
    roi_scale = _pct_from_rules(rules, "roi_scale", "AD_BID_ROI_SCALE", 0.55)
    roi_cut = _pct_from_rules(rules, "roi_cut", "AD_BID_ROI_CUT", 0.25)
    budget_up = _pct_from_rules(rules, "budget_up_pct", "AD_BID_BUDGET_UP_PCT", 0.15)
    budget_down = _pct_from_rules(rules, "budget_down_pct", "AD_BID_BUDGET_DOWN_PCT", 0.20)
    min_impressions = int(rules.get("min_impressions") or 500)

    action = "maintain"
    reason = "指标平稳，维持当前预算"
    new_budget = daily_budget_cny
    priority = 0
    rule_id = ""

    candidates: list[tuple[int, str, str, float, str]] = []

    if _rule_enabled(rules, "low_ctr") and impressions >= min_impressions and ctr < ctr_bad:
        candidates.append((
            3,
            "decrease_budget",
            f"CTR {ctr:.2%} 低于阈值 {ctr_bad:.2%}，降价 {budget_down:.0%}",
            round(daily_budget_cny * (1 - budget_down), 2),
            "low_ctr",
        ))
    if _rule_enabled(rules, "high_cpc") and cpc > cpc_max and clicks >= 5:
        candidates.append((
            3,
            "decrease_budget",
            f"CPC {cpc:.2f} 超过上限 {cpc_max}，降价 {budget_down:.0%}",
            round(daily_budget_cny * (1 - budget_down), 2),
            "high_cpc",
        ))
    if _rule_enabled(rules, "low_roi") and ad_roi_score < roi_cut and impressions >= 300:
        candidates.append((
            2,
            "decrease_budget",
            f"ROI 分 {ad_roi_score} 偏低，降价 {budget_down:.0%}",
            round(daily_budget_cny * (1 - budget_down), 2),
            "low_roi",
        ))
    if _rule_enabled(rules, "good_roi_ctr") and ad_roi_score >= roi_scale and ctr >= ctr_good:
        candidates.append((
            2,
            "increase_budget",
            f"ROI {ad_roi_score} + CTR {ctr:.2%} 良好，加价 {budget_up:.0%}",
            round(daily_budget_cny * (1 + budget_up), 2),
            "good_roi_ctr",
        ))
    if _rule_enabled(rules, "good_ctr") and ctr >= ctr_good and clicks >= 10:
        candidates.append((
            1,
            "increase_budget",
            f"CTR {ctr:.2%} 良好，小幅加价",
            round(daily_budget_cny * (1 + budget_up * 0.5), 2),
            "good_ctr",
        ))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        priority, action, reason, new_budget, rule_id = candidates[0]

    min_budget = _pct_from_rules(rules, "min_budget", "AD_BID_MIN_BUDGET", 30.0)
    max_budget = _pct_from_rules(rules, "max_budget", "AD_BID_MAX_BUDGET", 2000.0)
    new_budget = max(min_budget, min(max_budget, new_budget))

    if action != "maintain" and abs(new_budget - daily_budget_cny) < 1:
        action = "maintain"
        reason = "预算调整幅度过小，维持不变"
        rule_id = ""

    return {
        "action": action,
        "reason": reason,
        "rule_id": rule_id,
        "priority": priority,
        "current_budget_cny": round(daily_budget_cny, 2),
        "new_budget_cny": round(new_budget, 2),
        "delta_cny": round(new_budget - daily_budget_cny, 2),
        "metrics_snapshot": {"ctr": round(ctr, 4), "cpc": round(cpc, 2), "impressions": impressions, "clicks": clicks},
        "ad_roi_score": ad_roi_score,
    }


def apply_bid_decision(run_id: str, decision: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    """执行调价决策（调用投流 API 或 dry_run）。"""
    campaign = get_ad_campaign_by_run(run_id)
    if not campaign:
        return {"ok": False, "error": "no_campaign_for_run", "run_id": run_id}

    action = decision.get("action") or "maintain"
    if action == "maintain":
        return {"ok": True, "applied": False, "action": action, "message": decision.get("reason")}

    cid = str(campaign.get("campaign_id") or "")
    new_budget = float(decision.get("new_budget_cny") or campaign.get("daily_budget") or 0)
    if dry_run or bool(campaign.get("dry_run")):
        metrics_record(
            run_id=run_id,
            event_type="ad_bid_adjust",
            value=new_budget,
            payload={"action": action, "dry_run": True, **decision},
        )
        return {
            "ok": True,
            "applied": True,
            "dry_run": True,
            "campaign_id": cid,
            "action": action,
            "new_budget_cny": new_budget,
        }

    api_result = update_campaign_budget(campaign_id=cid, daily_budget_cny=new_budget)
    ok = bool(api_result.get("ok"))
    if ok:
        metrics_record(
            run_id=run_id,
            event_type="ad_bid_adjust",
            value=new_budget,
            payload={"action": action, "campaign_id": cid, **decision},
        )
    return {
        "ok": ok,
        "applied": ok,
        "campaign_id": cid,
        "action": action,
        "new_budget_cny": new_budget,
        "api_result": api_result,
    }


def run_auto_bid_for_run(run_id: str, *, apply: bool = True) -> dict[str, Any]:
    """读取最近报表 → 评估规则 → 可选执行调价。"""
    if not auto_bid_enabled():
        return {"ok": False, "error": "auto_bid_disabled"}

    campaign = get_ad_campaign_by_run(run_id)
    if not campaign:
        return {"ok": False, "error": "no_campaign_for_run", "run_id": run_id}

    last = campaign.get("last_report") or {}
    metrics = last.get("metrics") or {}
    if not metrics:
        return {"ok": False, "error": "no_report_metrics", "run_id": run_id}

    ad_roi = float(last.get("ad_roi_score") or 0)
    budget = float(campaign.get("daily_budget") or metrics.get("daily_budget_cny") or 100)
    decision = evaluate_bid_rules(metrics=metrics, ad_roi_score=ad_roi, daily_budget_cny=budget)

    result: dict[str, Any] = {"ok": True, "run_id": run_id, "decision": decision}
    if apply and decision.get("action") != "maintain":
        result["apply"] = apply_bid_decision(run_id, decision, dry_run=bool(campaign.get("dry_run")))
    else:
        result["apply"] = {"ok": True, "applied": False, "action": "maintain"}
    return result


def run_auto_bid_all(*, limit: int = 50, apply: bool = True) -> dict[str, Any]:
    from core.storage import list_ad_campaigns

    items = list_ad_campaigns(limit=limit)
    results = []
    for row in items:
        rid = str(row.get("run_id") or "")
        if not rid:
            continue
        results.append(run_auto_bid_for_run(rid, apply=apply))

    applied = sum(1 for r in results if (r.get("apply") or {}).get("applied"))
    return {"ok": True, "evaluated": len(results), "applied": applied, "results": results}
