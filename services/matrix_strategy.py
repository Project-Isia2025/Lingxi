"""联合 ROI 驱动矩阵发布策略。"""
from __future__ import annotations

import os
from typing import Any

from services.combined_roi import compute_combined_roi, resolve_run_roi_inputs
from services.publish.scheduler import matrix_publish_plan
from services.publish_priority import priority_from_combined_score


def matrix_roi_strategy_enabled() -> bool:
    return os.environ.get("MATRIX_ROI_STRATEGY_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def plan_matrix_from_combined_roi(run_id: str) -> dict[str, Any]:
    """根据联合 ROI 生成分平台/账号/优先级策略。"""
    if not matrix_roi_strategy_enabled():
        return {"ok": False, "error": "matrix_roi_strategy_disabled"}

    pub, ad = resolve_run_roi_inputs(run_id)
    combined = compute_combined_roi(publish_roi=pub, ad_roi=ad)
    if not combined.get("ok"):
        return {"ok": False, "error": "no_combined_roi", "run_id": run_id}

    score = float(combined["combined_roi_score"])
    grade = str(combined.get("grade") or "C")
    skip_below = float(os.environ.get("MATRIX_ROI_SKIP_BELOW", "0.3") or 0.3)

    if score < skip_below:
        return {
            "ok": True,
            "run_id": run_id,
            "action": "skip",
            "reason": f"联合 ROI {score} 低于阈值 {skip_below}，不建议矩阵分发",
            "combined": combined,
        }

    if score >= 0.75:
        platforms = ["douyin", "xiaohongshu"]
        accounts_per = int(os.environ.get("MATRIX_ROI_A_ACCOUNTS", "2") or 2)
        action = "full_matrix"
    elif score >= 0.55:
        platforms = ["douyin", "xiaohongshu"]
        accounts_per = 1
        action = "standard_matrix"
    elif score >= 0.35:
        platforms = ["douyin"]
        accounts_per = 1
        action = "single_platform"
    else:
        platforms = ["douyin"]
        accounts_per = 1
        action = "minimal"

    priority = priority_from_combined_score(score)

    return {
        "ok": True,
        "run_id": run_id,
        "action": action,
        "platforms": platforms,
        "accounts_per_platform": accounts_per,
        "priority": priority,
        "combined_roi_score": score,
        "grade": grade,
        "recommendation": combined.get("recommendation") or "",
        "components": combined.get("components") or {},
    }


def auto_matrix_publish(
    *,
    run_id: str,
    video_path: str,
    script: str,
    title: str = "",
    platforms: list[str] | None = None,
    org_id: str = "",
) -> dict[str, Any]:
    """联合 ROI 策略 → 多平台矩阵入队。"""
    plan = plan_matrix_from_combined_roi(run_id)
    if not plan.get("ok"):
        return plan
    if plan.get("action") == "skip":
        return plan

    plats = platforms or plan.get("platforms") or ["douyin"]
    priority = int(plan.get("priority") or 0)
    accounts_per = int(plan.get("accounts_per_platform") or 1)

    prev = os.environ.get("PUBLISH_ACCOUNTS_PER_PLATFORM")
    os.environ["PUBLISH_ACCOUNTS_PER_PLATFORM"] = str(accounts_per)
    try:
        out = matrix_publish_plan(
            video_path=video_path,
            script=script,
            title=title,
            platforms=plats,
            run_id=run_id,
            priority=priority,
            org_id=org_id,
        )
    finally:
        if prev is None:
            os.environ.pop("PUBLISH_ACCOUNTS_PER_PLATFORM", None)
        else:
            os.environ["PUBLISH_ACCOUNTS_PER_PLATFORM"] = prev

    out["strategy"] = plan
    try:
        from services.dashboard_hub import notify_dashboard_update

        notify_dashboard_update(reason="matrix_auto_publish")
    except Exception:
        pass
    return out
