"""全局 ROI 评分：综合各 Agent 产出与历史指标。"""
from __future__ import annotations

from typing import Any

from core.storage import metrics_summary


def compute_roi(ctx: Any) -> dict[str, Any]:
    """根据工作流上下文计算 ROI 及分项得分。"""
    perception = getattr(ctx, "perception", {}) or {}
    memory = getattr(ctx, "memory", {}) or {}
    strategy = getattr(ctx, "strategy", {}) or {}
    content = getattr(ctx, "content", {}) or {}
    execution = getattr(ctx, "execution", {}) or {}

    breakdown: dict[str, float] = {}
    total = 0.0

    # 数据感知
    comp_n = len(perception.get("competitors") or [])
    breakdown["perception_competitors"] = min(0.12, comp_n * 0.012)
    trend = (perception.get("traffic_trend") or {}).get("trend")
    breakdown["perception_trend"] = 0.08 if trend == "rising" else (0.03 if trend == "stable" else 0.01)
    vol = (perception.get("traffic_volatility") or {}).get("level")
    breakdown["perception_volatility"] = 0.05 if vol == "high_opportunity" else 0.02
    total += sum(breakdown.get(k, 0) for k in breakdown if k.startswith("perception"))

    # 记忆库
    sop_n = len(memory.get("sop_entries") or [])
    breakdown["memory_sop"] = min(0.08, sop_n * 0.008)
    if memory.get("viral_structure"):
        breakdown["memory_viral"] = 0.06
    total += sum(breakdown.get(k, 0) for k in breakdown if k.startswith("memory"))

    # 策略
    if strategy.get("product_selection"):
        breakdown["strategy_selection"] = 0.1
    if strategy.get("ad_plan"):
        breakdown["strategy_ad"] = 0.08
    if not (strategy.get("video_cost_plan") or {}).get("approval_required"):
        breakdown["strategy_budget"] = 0.05
    total += sum(breakdown.get(k, 0) for k in breakdown if k.startswith("strategy"))

    # 内容
    risk = content.get("risk_check") or {}
    if risk.get("passed"):
        breakdown["content_risk"] = 0.1
    if content.get("channel_contents"):
        breakdown["content_channels"] = 0.06
    if content.get("variants"):
        breakdown["content_variants"] = 0.04
    if not content.get("dedupe_duplicate"):
        breakdown["content_unique"] = 0.05
    total += sum(breakdown.get(k, 0) for k in breakdown if k.startswith("content"))

    # 执行
    if execution.get("published"):
        breakdown["execution_published"] = 0.15
    elif execution.get("auto_started"):
        breakdown["execution_queued"] = 0.05
    if execution.get("ad_optimize_plan"):
        breakdown["execution_ad"] = 0.06
    ad_report = execution.get("ad_report") or {}
    if ad_report.get("ad_roi_score"):
        breakdown["execution_ad_roi"] = min(0.12, float(ad_report["ad_roi_score"]) * 0.12)
    publish_roi = execution.get("publish_roi_score") or execution.get("roi_feedback", {}).get("publish_roi_score")
    if publish_roi:
        breakdown["execution_publish_roi"] = min(0.1, float(publish_roi) * 0.1)
    combined = execution.get("combined_roi") or execution.get("roi_feedback", {}).get("combined_roi") or {}
    if isinstance(combined, dict) and combined.get("combined_roi_score"):
        breakdown["execution_combined_roi"] = min(0.15, float(combined["combined_roi_score"]) * 0.15)
    total += sum(breakdown.get(k, 0) for k in breakdown if k.startswith("execution"))

    # 历史加成
    hist = metrics_summary(days=14)
    leads = int(hist.get("leads_total") or 0)
    pub = int((hist.get("by_event") or {}).get("publish_ok", {}).get("count") or 0)
    breakdown["history_leads"] = min(0.1, leads * 0.015)
    breakdown["history_publish"] = min(0.08, pub * 0.02)
    total += breakdown["history_leads"] + breakdown["history_publish"]

    score = min(1.0, round(total, 3))
    grade = "A" if score >= 0.75 else "B" if score >= 0.55 else "C" if score >= 0.35 else "D"

    return {
        "roi_score": score,
        "grade": grade,
        "breakdown": breakdown,
        "recommendation": _recommend(score, ctx),
    }


def _recommend(score: float, ctx: Any) -> str:
    execution = getattr(ctx, "execution", {}) or {}
    content = getattr(ctx, "content", {}) or {}
    if score >= 0.75 and not execution.get("published"):
        return "ROI 良好，建议开启 auto_publish 完成闭环"
    if content.get("dedupe_duplicate"):
        return "内容与历史稿重复度较高，建议调整角度或关键词后重跑"
    if score < 0.4:
        return "感知/内容数据不足，建议补充 reference_urls 或降低 min_likes 筛选"
    return "可进入小预算投流测试，关注 3 秒完播与 CTR"
