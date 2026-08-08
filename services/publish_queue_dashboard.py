"""发布队列 Dashboard 数据。"""

from __future__ import annotations



import time

from collections import Counter

from typing import Any





def build_publish_queue_dashboard(*, limit: int = 100, org_id: str = "") -> dict[str, Any]:

    from core.storage import list_publish_queue_items

    from services.publish_priority import dynamic_priority_enabled, enrich_queue_item

    from services.publish_rate_limit import rate_limit_config

    from services.publish_worker import get_worker_status

    from services.tenant import normalize_org_id, org_isolation_enabled



    oid = normalize_org_id(org_id)

    items = list_publish_queue_items(limit=max(10, min(limit, 300)), org_id=oid)

    now = int(time.time())



    by_status: Counter[str] = Counter()

    by_platform: Counter[str] = Counter()

    by_run: Counter[str] = Counter()

    due_now = 0

    scheduled_future = 0

    roi_adjustable = 0

    roi_locked = 0



    normalized: list[dict[str, Any]] = []

    for row in items:

        enriched = enrich_queue_item(row)

        st = str(enriched.get("status") or "unknown")

        plat = str(enriched.get("platform") or "")

        rid = str(enriched.get("run_id") or "")

        sched = int(enriched.get("scheduled_ts") or 0)

        by_status[st] += 1

        by_platform[plat] += 1

        if rid:

            by_run[rid] += 1

        if st == "queued":

            if sched <= now:

                due_now += 1

            else:

                scheduled_future += 1

            if enriched.get("priority_pinned") or enriched.get("priority_manual"):

                roi_locked += 1

            elif rid:

                roi_adjustable += 1

        normalized.append({

            "job_id": enriched.get("job_id"),

            "platform": plat,

            "account_id": enriched.get("account_id"),

            "title": enriched.get("title"),

            "script": (str(enriched.get("script") or ""))[:80],

            "run_id": rid,

            "status": st,

            "priority": int(enriched.get("priority") or 0),

            "suggested_priority": int(enriched.get("suggested_priority") or 0),

            "priority_delta": int(enriched.get("priority_delta") or 0),

            "priority_source": enriched.get("priority_source") or "default",

            "combined_roi_score": enriched.get("combined_roi_score"),

            "roi_grade": enriched.get("roi_grade") or "",

            "priority_pinned": bool(enriched.get("priority_pinned")),

            "priority_manual": bool(enriched.get("priority_manual")),

            "scheduled_ts": sched,

            "due_in_sec": max(0, sched - now) if st == "queued" else 0,

            "retry_count": int(enriched.get("retry_count") or 0),

            "last_error": str(enriched.get("last_error") or "")[:120],

            "updated_ts": int(enriched.get("updated_ts") or 0),

            "org_id": str(enriched.get("org_id") or ""),

        })



    normalized.sort(

        key=lambda x: (

            0 if x.get("status") == "queued" else 1,

            -int(x.get("priority") or 0),

            int(x.get("scheduled_ts") or 0),

        ),

    )



    top_runs = [

        {"run_id": rid, "count": cnt}

        for rid, cnt in by_run.most_common(8)

    ]



    return {

        "ok": True,

        "ts": now,

        "org_id": oid,

        "org_isolation": org_isolation_enabled(),

        "dynamic_priority": dynamic_priority_enabled(),

        "worker": get_worker_status(),

        "rate_limit": rate_limit_config(),

        "stats": {

            "total": len(items),

            "by_status": dict(by_status),

            "by_platform": dict(by_platform),

            "queued_due_now": due_now,

            "queued_scheduled": scheduled_future,

            "unique_runs": len(by_run),

            "top_runs": top_runs,

            "roi_adjustable": roi_adjustable,

            "roi_locked": roi_locked,

        },

        "items": normalized[:limit],

    }

