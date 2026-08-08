"""发布后完播率/CTR 监控、下架与重剪触发。"""
from __future__ import annotations

import os
import time
import uuid
from typing import Any

from core.storage import metrics_record, schedule_post_monitor, update_post_monitor


def monitor_enabled() -> bool:
    return os.environ.get("POST_PUBLISH_MONITOR_ENABLED", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def monitor_delay_sec() -> int:
    try:
        hours = float(os.environ.get("POST_PUBLISH_MONITOR_DELAY_HOURS", "24"))
        return max(300, int(hours * 3600))
    except ValueError:
        return 86400


def completion_rate_min() -> float:
    try:
        return float(os.environ.get("COMPLETION_RATE_MIN", "0.30"))
    except ValueError:
        return 0.30


def ctr_min() -> float:
    try:
        return float(os.environ.get("CTR_MIN", "0.008"))
    except ValueError:
        return 0.008


def schedule_monitor(
    *,
    run_id: str,
    platform: str,
    post_url: str,
    job_id: str = "",
    keyword: str = "",
    script: str = "",
) -> dict[str, Any]:
    if not monitor_enabled():
        return {"ok": False, "reason": "monitor_disabled"}
    mid = f"mon-{uuid.uuid4().hex[:12]}"
    due = int(time.time()) + monitor_delay_sec()
    schedule_post_monitor(
        monitor_id=mid,
        run_id=run_id,
        platform=platform,
        post_url=post_url,
        job_id=job_id,
        due_ts=due,
        payload={"keyword": keyword, "script_excerpt": (script or "")[:200]},
    )
    return {"ok": True, "monitor_id": mid, "due_ts": due}


def fetch_post_metrics(
    *,
    run_id: str,
    platform: str,
    post_url: str,
    account_id: str = "default",
) -> dict[str, Any]:
    """优先创作者中心回采，其次投流报表 CTR，再 ROI 代理/heuristic。"""
    ctr = None
    completion_rate = None
    source = "heuristic"
    extra: dict[str, Any] = {}

    try:
        from services.creator_center import creator_metrics_enabled, fetch_creator_post_metrics

        if creator_metrics_enabled() and (post_url or "").startswith("http"):
            cr = fetch_creator_post_metrics(
                platform=platform,
                post_url=post_url,
                account_id=account_id,
            )
            if cr.get("ok"):
                if cr.get("completion_rate") is not None:
                    completion_rate = float(cr["completion_rate"])
                if cr.get("ctr") is not None:
                    ctr = float(cr["ctr"])
                source = str(cr.get("source") or "creator_center")
                for key in ("views", "likes", "hint", "post_id", "account_id"):
                    if cr.get(key) is not None:
                        extra[key] = cr[key]
    except Exception:
        pass

    if run_id:
        try:
            from services.ad_feedback import sync_ad_report_for_run

            ad = sync_ad_report_for_run(run_id)
            report = ad.get("report") or ad if isinstance(ad, dict) else {}
            metrics = report.get("metrics") or report
            if isinstance(metrics, dict):
                raw_ctr = metrics.get("ctr") or metrics.get("click_rate")
                if raw_ctr is not None:
                    ctr = float(raw_ctr)
                    source = "ad_report"
        except Exception:
            pass

    try:
        from core.storage import metrics_for_run

        rows = metrics_for_run(run_id, limit=30) if run_id else []
        for row in rows:
            if row.get("event_type") == "publish_roi":
                roi = float(row.get("metric_value") or 0)
                completion_rate = round(min(0.95, max(0.15, roi * 0.85)), 4)
                if source == "heuristic":
                    source = "publish_roi_proxy"
                break
    except Exception:
        pass

    if completion_rate is None:
        completion_rate = 0.42 if post_url.startswith("http") else 0.25

    if ctr is None:
        ctr = round(min(0.05, max(0.004, completion_rate * 0.06)), 4)

    return {
        "ok": True,
        "run_id": run_id,
        "platform": platform,
        "post_url": post_url,
        "completion_rate": completion_rate,
        "ctr": ctr,
        "source": source,
        **extra,
    }


def trigger_reedit(*, run_id: str, reason: str, platform: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """低指标触发重剪：写入 episodic + 标记 content replan。"""
    from core.storage import save_episodic

    save_episodic(
        run_id=run_id or "reedit",
        agent="orchestrator",
        observation=f"发布后低指标触发重剪：{reason}",
        action="post_publish_reedit",
        payload={"platform": platform, "reason": reason, **(payload or {})},
    )
    metrics_record(
        run_id=run_id or "reedit",
        event_type="reedit_trigger",
        value=1.0,
        payload={"reason": reason, "platform": platform},
    )
    return {"ok": True, "run_id": run_id, "reason": reason, "reedit": True}


def poll_monitor(monitor: dict[str, Any]) -> dict[str, Any]:
    mid = str(monitor.get("monitor_id") or "")
    run_id = str(monitor.get("run_id") or "")
    platform = str(monitor.get("platform") or "")
    post_url = str(monitor.get("post_url") or "")

    metrics = fetch_post_metrics(run_id=run_id, platform=platform, post_url=post_url)
    comp = float(metrics.get("completion_rate") or 0)
    ctr = float(metrics.get("ctr") or 0)

    metrics_record(
        run_id=run_id or mid,
        event_type="completion_rate",
        value=comp,
        payload={"ctr": ctr, "post_url": post_url, "platform": platform, **metrics},
    )

    low = comp < completion_rate_min() or ctr < ctr_min()
    result: dict[str, Any] = {
        "ok": True,
        "monitor_id": mid,
        "metrics": metrics,
        "low_performance": low,
    }

    if low:
        from services.takedown import takedown_post

        reason = f"完播率 {comp:.2%} / CTR {ctr:.3%} 低于阈值"
        takedown = takedown_post(platform=platform, post_url=post_url, run_id=run_id, reason=reason)
        reedit = trigger_reedit(run_id=run_id, reason=reason, platform=platform, payload=metrics)
        update_post_monitor(
            monitor_id=mid,
            status="takedown_reedit",
            completion_rate=comp,
            ctr=ctr,
            payload={"takedown": takedown, "reedit": reedit, "metrics": metrics},
        )
        result["takedown"] = takedown
        result["reedit"] = reedit
    else:
        update_post_monitor(
            monitor_id=mid,
            status="ok",
            completion_rate=comp,
            ctr=ctr,
            payload={"metrics": metrics},
        )

    return result


def poll_due_monitors(*, limit: int = 5) -> dict[str, Any]:
    from core.storage import list_due_post_monitors

    due = list_due_post_monitors(limit=limit)
    results = [poll_monitor(m) for m in due]
    return {"ok": True, "polled": len(results), "results": results}
