"""发布队列动态优先级（基于联合 ROI）。"""

from __future__ import annotations



import os

import time

from typing import Any



from core.storage import list_publish_queue_items, metrics_latest, update_publish_queue_priority

from services.combined_roi import compute_combined_roi, resolve_run_roi_inputs





def dynamic_priority_enabled() -> bool:

    return os.environ.get("PUBLISH_DYNAMIC_PRIORITY", "1").strip().lower() not in ("0", "false", "no", "off")





def roi_auto_refresh_enabled() -> bool:

    return os.environ.get("PUBLISH_ROI_AUTO_REFRESH", "1").strip().lower() not in ("0", "false", "no", "off")





def priority_from_combined_score(score: float | None) -> int:

    if score is None:

        return int(os.environ.get("PUBLISH_QUEUE_RUN_PRIORITY", "5") or 5)

    if score >= 0.75:

        return int(os.environ.get("PUBLISH_PRIORITY_HIGH", "15") or 15)

    if score >= 0.55:

        return int(os.environ.get("PUBLISH_PRIORITY_MID", "10") or 10)

    if score >= 0.35:

        return int(os.environ.get("PUBLISH_PRIORITY_LOW", "5") or 5)

    return int(os.environ.get("PUBLISH_PRIORITY_MIN", "2") or 2)





def get_run_priority_context(run_id: str) -> dict[str, Any]:

    """解析 run 的联合 ROI 与建议优先级。"""

    if not run_id:

        return {

            "run_id": "",

            "combined_roi_score": None,

            "grade": "",

            "suggested_priority": int(os.environ.get("PUBLISH_QUEUE_RUN_PRIORITY", "5") or 5),

            "mode": "default",

        }



    combined = metrics_latest(run_id, "combined_roi")

    grade = ""

    mode = "cached"

    if combined is None:

        pub, ad = resolve_run_roi_inputs(run_id)

        calc = compute_combined_roi(publish_roi=pub, ad_roi=ad)

        if calc.get("ok"):

            combined = float(calc["combined_roi_score"])

            grade = str(calc.get("grade") or "")

            mode = str(calc.get("mode") or "computed")

        else:

            mode = "no_roi"

    else:

        grade = "A" if combined >= 0.75 else "B" if combined >= 0.55 else "C" if combined >= 0.35 else "D"



    return {

        "run_id": run_id,

        "combined_roi_score": combined,

        "grade": grade,

        "suggested_priority": priority_from_combined_score(combined),

        "mode": mode,

    }





def priority_locked(job: dict[str, Any]) -> bool:

    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}

    return bool(payload.get("priority_manual") or payload.get("priority_pinned"))





def priority_source(job: dict[str, Any]) -> str:

    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}

    if payload.get("priority_pinned"):

        return "pinned"

    if payload.get("priority_manual"):

        return "manual"

    if payload.get("priority_auto_ts"):

        return "roi"

    return "default"





def resolve_publish_priority(run_id: str = "", explicit: int = 0) -> int:

    """解析任务优先级：显式 > 联合 ROI > 默认。"""

    if explicit > 0:

        return int(explicit)

    if not dynamic_priority_enabled() or not run_id:

        return int(explicit or 0)



    ctx = get_run_priority_context(run_id)

    return int(ctx["suggested_priority"])





def refresh_queue_priorities(

    *,

    limit: int = 100,

    org_id: str = "",

    force: bool = False,

) -> dict[str, Any]:

    """刷新 queued 任务优先级，返回 diff 明细。"""

    if not dynamic_priority_enabled():

        return {"ok": False, "error": "dynamic_priority_disabled"}



    jobs = list_publish_queue_items(status="queued", limit=limit, org_id=org_id)

    updated = 0

    skipped_locked = 0

    unchanged = 0

    details: list[dict[str, Any]] = []

    for job in jobs:

        rid = str(job.get("run_id") or "")

        if not rid:

            unchanged += 1

            continue

        if not force and priority_locked(job):

            skipped_locked += 1

            continue



        ctx = get_run_priority_context(rid)

        new_pri = resolve_publish_priority(rid)

        old_pri = int(job.get("priority") or 0)

        if new_pri == old_pri:

            unchanged += 1

            continue



        update_publish_queue_priority(

            str(job["job_id"]),

            new_pri,

            source="auto",

            roi_meta={

                "combined_roi_score": ctx.get("combined_roi_score"),

                "grade": ctx.get("grade"),

                "priority_delta": new_pri - old_pri,

            },

        )

        updated += 1

        details.append({

            "job_id": job["job_id"],

            "run_id": rid,

            "old": old_pri,

            "new": new_pri,

            "delta": new_pri - old_pri,

            "combined_roi_score": ctx.get("combined_roi_score"),

            "grade": ctx.get("grade"),

        })



    result = {

        "ok": True,

        "checked": len(jobs),

        "updated": updated,

        "unchanged": unchanged,

        "skipped_locked": skipped_locked,

        "details": details[:30],

        "ts": int(time.time()),

    }

    if updated:

        _notify_refresh(result)

    return result





def refresh_priorities_for_run(run_id: str, *, force: bool = False) -> dict[str, Any]:

    """联合 ROI 更新后，刷新指定 run 的队列任务。"""

    if not run_id or not roi_auto_refresh_enabled():

        return {"ok": False, "error": "disabled_or_no_run_id"}

    jobs = list_publish_queue_items(status="queued", limit=200)

    matched = [j for j in jobs if str(j.get("run_id") or "") == run_id]

    if not matched:

        return {"ok": True, "run_id": run_id, "updated": 0, "details": []}



    updated = 0

    details = []

    ctx = get_run_priority_context(run_id)

    new_pri = resolve_publish_priority(run_id)

    for job in matched:

        if not force and priority_locked(job):

            continue

        old_pri = int(job.get("priority") or 0)

        if new_pri == old_pri:

            continue

        update_publish_queue_priority(

            str(job["job_id"]),

            new_pri,

            source="auto",

            roi_meta={

                "combined_roi_score": ctx.get("combined_roi_score"),

                "grade": ctx.get("grade"),

                "priority_delta": new_pri - old_pri,

            },

        )

        updated += 1

        details.append({"job_id": job["job_id"], "old": old_pri, "new": new_pri, "delta": new_pri - old_pri})



    out = {"ok": True, "run_id": run_id, "updated": updated, "details": details, "context": ctx}

    if updated:

        _notify_refresh(out)

    return out





def enrich_queue_item(job: dict[str, Any]) -> dict[str, Any]:

    """为 Dashboard 补充 ROI 优先级上下文。"""

    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}

    rid = str(job.get("run_id") or "")

    ctx = get_run_priority_context(rid) if rid else {}

    old_pri = int(job.get("priority") or 0)

    suggested = int(ctx.get("suggested_priority") or old_pri)

    return {

        **job,

        "priority_source": priority_source(job),

        "combined_roi_score": ctx.get("combined_roi_score"),

        "roi_grade": ctx.get("grade") or "",

        "suggested_priority": suggested,

        "priority_delta": suggested - old_pri if suggested != old_pri else int(payload.get("priority_delta") or 0),

        "priority_pinned": bool(payload.get("priority_pinned")),

        "priority_manual": bool(payload.get("priority_manual")),

    }





def _notify_refresh(result: dict[str, Any]) -> None:

    try:

        from services.dashboard_hub import notify_dashboard_update



        notify_dashboard_update(reason="publish_priority_refresh")

    except Exception:

        pass

