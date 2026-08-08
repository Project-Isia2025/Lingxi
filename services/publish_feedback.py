"""发布成功 ROI 回写闭环。"""
from __future__ import annotations

import os
from typing import Any

from core.storage import kb_boost_roi, kb_search, kb_upsert, metrics_record, save_episodic
from services.knowledge import ingest_content_feedback


def publish_feedback_enabled() -> bool:
    return os.environ.get("PUBLISH_ROI_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def compute_publish_roi_score(
    *,
    platform: str,
    post_url: str = "",
    script: str = "",
    account_id: str = "default",
) -> float:
    """根据发布结果估算内容 ROI 分（0~1）。"""
    score = 0.45
    if post_url.startswith("http"):
        score += 0.25
    script_len = len((script or "").strip())
    if script_len >= 200:
        score += 0.15
    elif script_len >= 80:
        score += 0.08
    if platform in ("douyin", "xiaohongshu", "xhs"):
        score += 0.05
    if account_id and account_id != "default":
        score += 0.02
    return min(1.0, round(score, 3))


def apply_publish_success_feedback(
    *,
    platform: str,
    script: str,
    title: str = "",
    post_url: str = "",
    run_id: str = "",
    account_id: str = "default",
    job_id: str = "",
    keyword: str = "",
) -> dict[str, Any]:
    """发布成功后写入 metrics、知识库 ROI 与 episodic。"""
    if not publish_feedback_enabled():
        return {"ok": False, "reason": "publish_roi_disabled"}

    plat = platform.strip().lower()
    if plat == "xhs":
        plat = "xiaohongshu"
    rid = run_id or (f"pub-{job_id}" if job_id else f"pub-{plat}-{account_id}")
    publish_roi = compute_publish_roi_score(
        platform=plat,
        post_url=post_url,
        script=script,
        account_id=account_id,
    )

    payload = {
        "platform": plat,
        "account_id": account_id,
        "post_url": post_url,
        "title": title,
        "job_id": job_id,
        "publish_roi_score": publish_roi,
    }
    metrics_record(run_id=rid, event_type="publish_ok", value=1.0, payload=payload)
    metrics_record(run_id=rid, event_type="publish_roi", value=publish_roi, payload=payload)

    kb_id = None
    kw = keyword or (title or script[:20]).strip()
    if script.strip():
        fb = ingest_content_feedback(
            run_id=rid,
            script=script,
            keyword=kw or "发布",
            platform=plat,
            published=True,
        )
        kb_id = fb.get("kb_id")
    elif post_url:
        kb_id = kb_upsert(
            library="hotspot",
            title=f"发布成功·{title or kw or plat}",
            body=f"平台={plat} 链接={post_url}",
            tags=f"{kw},publish_feedback",
            platform=plat,
        )

    if publish_roi >= 0.6 and kw:
        hits = kb_search(query=kw, library="hotspot", limit=3)
        for hit in hits:
            kb_boost_roi(item_id=int(hit["id"]), delta=min(0.4, publish_roi * 0.25))

    save_episodic(
        run_id=rid,
        agent="execution",
        observation=f"发布成功 ROI={publish_roi}",
        action="publish_roi_feedback",
        payload={"kb_id": kb_id, **payload},
    )

    combined = None
    if run_id:
        try:
            from services.combined_roi import apply_combined_roi_for_run

            combined = apply_combined_roi_for_run(run_id, keyword=kw)
            payload["combined_roi"] = combined
        except Exception:
            pass

    try:
        from services.dashboard_hub import notify_dashboard_update

        notify_dashboard_update(reason="publish_success")
    except Exception:
        pass

    monitor = None
    if post_url and run_id:
        try:
            from services.post_publish_monitor import schedule_monitor

            monitor = schedule_monitor(
                run_id=rid,
                platform=plat,
                post_url=post_url,
                job_id=job_id,
                keyword=kw,
                script=script,
            )
        except Exception:
            pass

    try:
        from services.roi_alert import dispatch_roi_alerts

        dispatch_roi_alerts(
            run_id=rid,
            publish_roi=publish_roi,
            event="publish_success",
            extra={"platform": plat, "post_url": post_url},
        )
    except Exception:
        pass

    return {
        "ok": True,
        "run_id": rid,
        "publish_roi_score": publish_roi,
        "kb_id": kb_id,
        "combined_roi": combined,
        "recommendation": _publish_recommend(publish_roi, plat),
        "post_monitor": monitor,
    }


def _publish_recommend(publish_roi: float, platform: str) -> str:
    if publish_roi >= 0.75:
        return f"{platform} 发布质量高，建议同脚本矩阵分发并投流放大"
    if publish_roi >= 0.55:
        return "发布完成，建议 24h 后同步投流报表观察 ROI"
    return "发布成功，建议补充标题/标签后观察互动数据"


def apply_publish_failure_feedback(
    *,
    platform: str,
    error: str,
    run_id: str = "",
    job_id: str = "",
    retry_count: int = 0,
) -> dict[str, Any]:
    rid = run_id or (f"pub-{job_id}" if job_id else "pub-anon")
    metrics_record(
        run_id=rid,
        event_type="publish_fail",
        value=float(retry_count),
        payload={"platform": platform, "error": error, "retry_count": retry_count},
    )
    try:
        from services.roi_alert import dispatch_roi_alerts

        dispatch_roi_alerts(run_id=rid, event="publish_fail", extra={"platform": platform, "error": error})
    except Exception:
        pass
    return {"ok": True, "run_id": rid, "error": error, "retry_count": retry_count}
