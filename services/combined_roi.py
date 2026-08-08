"""发布 ROI + 投流 ROI 联合评分。"""
from __future__ import annotations

import os
from typing import Any

from core.storage import get_ad_campaign_by_run, kb_upsert, metrics_latest, metrics_record, save_episodic
from services.ad_feedback import compute_ad_roi_score


def combined_roi_enabled() -> bool:
    return os.environ.get("COMBINED_ROI_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def _weight(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def compute_combined_roi(
    *,
    publish_roi: float | None = None,
    ad_roi: float | None = None,
) -> dict[str, Any]:
    """加权合并发布分与投流分（0~1）。"""
    pub = publish_roi
    ad = ad_roi
    w_pub = _weight("COMBINED_ROI_PUBLISH_WEIGHT", 0.4)
    w_ad = _weight("COMBINED_ROI_AD_WEIGHT", 0.6)

    components: dict[str, float | None] = {"publish_roi": pub, "ad_roi": ad}
    if pub is not None and ad is not None:
        score = min(1.0, round(pub * w_pub + ad * w_ad, 3))
        if pub >= 0.6 and ad >= 0.5:
            score = min(1.0, round(score + 0.05, 3))
        mode = "blended"
    elif pub is not None:
        score = pub
        mode = "publish_only"
    elif ad is not None:
        score = ad
        mode = "ad_only"
    else:
        return {"ok": False, "error": "no_roi_inputs", "components": components}

    grade = "A" if score >= 0.75 else "B" if score >= 0.55 else "C" if score >= 0.35 else "D"
    return {
        "ok": True,
        "combined_roi_score": score,
        "grade": grade,
        "mode": mode,
        "components": components,
        "weights": {"publish": w_pub, "ad": w_ad},
        "recommendation": _recommend(score, pub, ad),
    }


def _recommend(combined: float, pub: float | None, ad: float | None) -> str:
    if combined >= 0.75 and pub and ad and pub >= 0.6 and ad >= 0.55:
        return "内容与投流双优，建议矩阵复制并加预算 15%"
    if pub and pub >= 0.7 and (ad is None or ad < 0.4):
        return "发布质量高但投流待验证，建议小预算测试并 24h 同步报表"
    if ad and ad >= 0.6 and (pub is None or pub < 0.5):
        return "投流表现好，建议优化钩子/封面提升自然流"
    if combined >= 0.55:
        return "综合 ROI 中等，维持观察并 A/B 测试标题"
    return "综合 ROI 偏低，建议换角度或暂停投流"


def resolve_run_roi_inputs(run_id: str) -> tuple[float | None, float | None]:
    publish_roi = metrics_latest(run_id, "publish_roi")
    ad_roi = metrics_latest(run_id, "ad_roi")
    if ad_roi is None:
        campaign = get_ad_campaign_by_run(run_id)
        if campaign:
            last = campaign.get("last_report") or {}
            if last.get("ad_roi_score") is not None:
                ad_roi = float(last["ad_roi_score"])
            elif last.get("metrics"):
                ad_roi = compute_ad_roi_score(last["metrics"])
    return publish_roi, ad_roi


def apply_combined_roi_for_run(run_id: str, *, keyword: str = "") -> dict[str, Any]:
    """读取 run 的发布/投流分并写入 combined_roi 指标与知识库。"""
    if not combined_roi_enabled() or not run_id:
        return {"ok": False, "error": "disabled_or_no_run_id"}

    pub, ad = resolve_run_roi_inputs(run_id)
    result = compute_combined_roi(publish_roi=pub, ad_roi=ad)
    if not result.get("ok"):
        return result

    score = float(result["combined_roi_score"])
    payload = {**result, "run_id": run_id, "keyword": keyword}
    metrics_record(run_id=run_id, event_type="combined_roi", value=score, payload=payload)

    kw = keyword or run_id[:12]
    kb_upsert(
        library="hotspot",
        title=f"联合ROI·{kw} ({result['grade']})",
        body=(
            f"综合分={score} 发布={pub} 投流={ad}\n"
            f"建议：{result.get('recommendation') or ''}"
        )[:2000],
        tags=f"{kw},combined_roi,auto_ingest",
        platform="all",
    )
    save_episodic(
        run_id=run_id,
        agent="orchestrator",
        observation=f"联合 ROI={score} ({result.get('mode')})",
        action="combined_roi_feedback",
        payload=payload,
    )

    try:
        from services.dashboard_hub import notify_dashboard_update

        notify_dashboard_update(reason="combined_roi")
    except Exception:
        pass

    bid_result = None
    try:
        from services.combined_roi_bid import run_combined_roi_bid_for_run

        bid_result = run_combined_roi_bid_for_run(run_id, apply=True)
    except Exception:
        pass

    try:
        from services.roi_alert import dispatch_roi_alerts

        dispatch_roi_alerts(
            run_id=run_id,
            combined_roi=score,
            publish_roi=pub,
            ad_roi=ad,
            event="combined_roi",
            extra={"keyword": keyword},
        )
    except Exception:
        pass

    priority_refresh = None
    try:
        from services.publish_priority import refresh_priorities_for_run

        priority_refresh = refresh_priorities_for_run(run_id)
    except Exception:
        pass

    return {
        "ok": True,
        "run_id": run_id,
        "combined_roi_bid": bid_result,
        "priority_refresh": priority_refresh,
        **result,
    }
