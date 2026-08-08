"""投流调优：出价建议、预算分配、素材测试计划 + API 同步。"""
from __future__ import annotations

from typing import Any

from services.ad_traffic.client import ad_api_enabled, sync_ad_plan_to_api


def build_ad_plan(    *,
    keyword: str,
    platform: str,
    strategy: dict[str, Any],
    perception: dict[str, Any],
    budget_limit: float = 0,
) -> dict[str, Any]:
    trend = perception.get("traffic_trend") or {}
    trend_name = trend.get("trend") or "stable"
    competitors = perception.get("competitors") or []
    top_likes = 0
    if competitors:
        try:
            top_likes = int(competitors[0].get("likes") or 0)
        except (TypeError, ValueError):
            top_likes = 0

    daily_budget = float(budget_limit or 0) or 100.0
    if trend_name == "cold_start":
        daily_budget = min(daily_budget, 80.0)
        phase = "explore"
        bid_strategy = "低出价广覆盖，优先完播率>30%"
    elif trend_name == "rising":
        daily_budget = min(daily_budget * 1.2, 500.0)
        phase = "scale"
        bid_strategy = "逐步提价 10-20%，锁定高转化人群包"
    else:
        phase = "maintain"
        bid_strategy = "稳定出价，替换 CTR<1.5% 素材"

    cpm_est = 25.0 if platform in ("douyin", "tiktok") else 35.0
    if top_likes >= 5000:
        cpm_est *= 1.15

    tests = [
        {"variant": "A", "focus": "痛点钩子", "budget_pct": 40, "kpi": "3s完播率>35%"},
        {"variant": "B", "focus": "案例证据", "budget_pct": 35, "kpi": "CTR>2%"},
        {"variant": "C", "focus": "强CTA转化", "budget_pct": 25, "kpi": "私信成本<15元"},
    ]

    plan = {
        "phase": phase,
        "platform": platform,
        "keyword": keyword,
        "daily_budget_cny": round(daily_budget, 2),
        "estimated_cpm": round(cpm_est, 2),
        "bid_strategy": bid_strategy,
        "ocpm_target": "私信转化" if platform in ("douyin", "shipinhao") else "互动",
        "audience_hint": f"兴趣：{keyword}相关；排除已转化用户",
        "creative_tests": tests,
        "optimize_rules": [
            "运行 24h 后暂停 CTR 最低素材",
            "完播率>40% 的素材加预算 20%",
            "CPA 超目标 1.5 倍则降价或换素材",
            "每周至少更新 2 条新脚本做 A/B",
        ],
        "schedule": {"start": "次日 10:00", "peak_hours": "12:00-14:00, 19:00-22:00"},
    }
    if ad_api_enabled():
        plan["api_mode"] = "live"
    else:
        plan["api_mode"] = "heuristic"
    return plan


def deploy_ad_plan(ad_plan: dict[str, Any], *, run_id: str = "", sync_api: bool = True) -> dict[str, Any]:
    """部署投流计划：本地计划 + 可选 API 创建 campaign。"""
    from core.storage import save_ad_campaign
    from services.ad_traffic.client import create_campaign, sync_ad_plan_to_api

    result: dict[str, Any] = {"plan": ad_plan, "deployed": False}
    created: dict[str, Any] = {}

    if sync_api:
        if ad_api_enabled():
            api_result = sync_ad_plan_to_api(ad_plan, run_id=run_id)
            result["api"] = api_result
            created = api_result.get("create_result") or {}
            result["deployed"] = bool(created.get("ok"))
        else:
            created = create_campaign(
                name=f"{ad_plan.get('keyword', 'campaign')}_{run_id[:8] if run_id else 'run'}"[:50],
                daily_budget_cny=float(ad_plan.get("daily_budget_cny") or 100),
                platform=str(ad_plan.get("platform") or "douyin"),
                keyword=str(ad_plan.get("keyword") or ""),
            )
            result["dry_run"] = True
            result["deployed"] = bool(created.get("ok"))
            result["message"] = created.get("message") or "投流 API 未配置，已生成模拟 campaign"

    cid = str(created.get("campaign_id") or "")
    if cid:
        result["campaign_id"] = cid
    if run_id and cid:
        save_ad_campaign(
            run_id=run_id,
            campaign_id=cid,
            platform=str(ad_plan.get("platform") or "douyin"),
            keyword=str(ad_plan.get("keyword") or ""),
            daily_budget=float(ad_plan.get("daily_budget_cny") or 0),
            dry_run=bool(created.get("dry_run") or result.get("dry_run")),
        )
    return result