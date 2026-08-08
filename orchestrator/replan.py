"""Plan → Observe → Replan 循环逻辑。"""
from __future__ import annotations

import os
from typing import Any

from orchestrator.context import WorkflowContext


def observe(ctx: WorkflowContext) -> dict[str, Any]:
    """汇总各 Agent 产出，生成观察报告。"""
    perception = ctx.perception or {}
    content = ctx.content or {}
    execution = ctx.execution or {}
    strategy = ctx.strategy or {}

    comp_n = len(perception.get("competitors") or [])
    crawl_source = (perception.get("crawl_meta") or {}).get("source") or "unknown"
    script_len = len(str(content.get("script") or ""))
    risk_ok = bool((content.get("risk_check") or {}).get("passed"))
    dup = bool(content.get("dedupe_duplicate"))
    qg = execution.get("quality_gate") or {}
    published = bool(execution.get("published"))
    has_ad = bool(strategy.get("ad_plan") or execution.get("ad_optimize_plan"))
    post_metrics = execution.get("post_publish_metrics") or {}

    issues: list[dict[str, Any]] = []
    if comp_n == 0:
        issues.append({"code": "no_competitors", "severity": "high", "message": "未获取竞品数据"})
    elif crawl_source == "curated":
        issues.append({"code": "crawler_fallback", "severity": "medium", "message": "爬虫回退样本库"})
    if script_len < 30:
        issues.append({"code": "script_too_short", "severity": "high", "message": "脚本过短"})
    if dup:
        issues.append({"code": "content_duplicate", "severity": "medium", "message": "内容与历史重复"})
    if not risk_ok:
        issues.append({"code": "risk_failed", "severity": "high", "message": "风控未通过"})
    if ctx.goal.auto_publish and not qg.get("passed"):
        issues.append({"code": "quality_gate", "severity": "high", "message": "质检未通过"})
    if ctx.goal.auto_publish and not published and not ctx.goal.video_path:
        issues.append({"code": "missing_video", "severity": "medium", "message": "缺少 video_path"})

    completion_rate = post_metrics.get("completion_rate")
    ctr = post_metrics.get("ctr")
    try:
        comp_min = float(os.environ.get("COMPLETION_RATE_MIN", "0.30"))
        ctr_min = float(os.environ.get("CTR_MIN", "0.008"))
    except ValueError:
        comp_min, ctr_min = 0.30, 0.008
    if completion_rate is not None and float(completion_rate) < comp_min:
        issues.append({
            "code": "low_completion_rate",
            "severity": "high",
            "message": f"完播率 {float(completion_rate):.2%} 低于 {comp_min:.0%}",
        })
    if ctr is not None and float(ctr) < ctr_min:
        issues.append({
            "code": "low_ctr",
            "severity": "high",
            "message": f"CTR {float(ctr):.3%} 低于 {ctr_min:.3%}",
        })

    score = 1.0
    score -= 0.25 * sum(1 for i in issues if i["severity"] == "high")
    score -= 0.1 * sum(1 for i in issues if i["severity"] == "medium")
    score = max(0.0, round(score, 3))

    return {
        "iteration": ctx.plan.get("iteration", 1),
        "observation_score": score,
        "competitors_count": comp_n,
        "crawl_source": crawl_source,
        "script_length": script_len,
        "risk_ok": risk_ok,
        "duplicate": dup,
        "quality_passed": qg.get("passed"),
        "published": published,
        "has_ad_plan": has_ad,
        "completion_rate": completion_rate,
        "ctr": ctr,
        "issues": issues,
        "needs_replan": score < 0.65 or any(i["severity"] == "high" for i in issues),
    }


def replan(ctx: WorkflowContext, observation: dict[str, Any]) -> dict[str, Any]:
    """根据观察结果调整计划，决定重跑哪些 Agent。"""
    issues = {i["code"] for i in observation.get("issues") or []}
    rerun: list[str] = []
    actions: list[str] = []

    if "no_competitors" in issues or "crawler_fallback" in issues:
        rerun.append("data_perception")
        goal = ctx.goal
        if goal.min_likes > 0:
            goal.min_likes = max(0, goal.min_likes // 2)
            actions.append("降低 min_likes 并重跑感知")
        else:
            actions.append("重跑数据感知")

    if "script_too_short" in issues or "content_duplicate" in issues or "risk_failed" in issues:
        rerun.append("content")
        if "content_duplicate" in issues:
            extra = ctx.goal.extra or {}
            extra["content_variant"] = "B"
            ctx.goal.extra = extra
            actions.append("切换 variant B 并重跑内容")
        else:
            actions.append("重跑内容生成")

    if "quality_gate" in issues and "content" not in rerun:
        rerun.append("content")
        actions.append("质检失败，重跑内容")

    if "low_completion_rate" in issues or "low_ctr" in issues:
        rerun.append("content")
        extra = ctx.goal.extra or {}
        extra["content_variant"] = "B"
        extra["reedit_from_post_publish"] = True
        ctx.goal.extra = extra
        actions.append("低完播/CTR，触发下架后重剪内容")

    if not rerun and observation.get("needs_replan"):
        rerun.append("strategy")
        actions.append("调整策略后重跑")

    iteration = int(ctx.plan.get("iteration") or 1) + 1
    plan = dict(ctx.plan or {})
    plan["iteration"] = iteration
    plan["replan_reason"] = actions or ["观察分数偏低，微调策略"]
    plan["rerun_agents"] = rerun
    plan["last_observation"] = observation
    ctx.plan = plan

    return {
        "iteration": iteration,
        "rerun_agents": rerun,
        "actions": actions,
        "should_continue": bool(rerun),
    }


def should_stop(ctx: WorkflowContext, observation: dict[str, Any]) -> bool:
    max_iter = int(getattr(ctx.goal, "max_iterations", 1) or 1)
    if not getattr(ctx.goal, "enable_replan", False):
        return True
    iteration = int(ctx.plan.get("iteration") or 1)
    if iteration >= max_iter:
        return True
    if not observation.get("needs_replan"):
        return True
    return False
