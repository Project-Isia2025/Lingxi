"""发布队列运维：手动优先级、取消、改期。"""
from __future__ import annotations

import time
from typing import Any


def set_job_priority(*, job_id: str, priority: int, org_id: str = "") -> dict[str, Any]:
    from core.storage import get_publish_queue_job, update_publish_queue_priority
    from services.tenant import assert_org_access

    job = get_publish_queue_job(job_id)
    if not job:
        return {"ok": False, "error": "job_not_found", "job_id": job_id}
    ok, err = assert_org_access(job, org_id)
    if not ok:
        return {"ok": False, "error": err, "job_id": job_id}
    if str(job.get("status") or "") != "queued":
        return {"ok": False, "error": "job_not_queued", "status": job.get("status")}

    pri = max(0, min(100, int(priority)))
    update_publish_queue_priority(job_id, pri, source="manual")
    _notify()
    return {"ok": True, "job_id": job_id, "priority": pri}


def bump_job_priority(*, job_id: str, delta: int = 5, org_id: str = "") -> dict[str, Any]:
    from core.storage import get_publish_queue_job

    job = get_publish_queue_job(job_id)
    if not job:
        return {"ok": False, "error": "job_not_found"}
    payload = dict(job.get("payload") or {})
    old = int(payload.get("priority") or job.get("priority") or 0)
    return set_job_priority(job_id=job_id, priority=old + int(delta), org_id=org_id)


def pin_job_priority(*, job_id: str, org_id: str = "") -> dict[str, Any]:
    import os

    from core.storage import get_publish_queue_job, update_publish_queue_priority
    from services.tenant import assert_org_access

    job = get_publish_queue_job(job_id)
    if not job:
        return {"ok": False, "error": "job_not_found"}
    ok, err = assert_org_access(job, org_id)
    if not ok:
        return {"ok": False, "error": err}
    if str(job.get("status") or "") != "queued":
        return {"ok": False, "error": "job_not_queued", "status": job.get("status")}

    high = int(os.environ.get("PUBLISH_PRIORITY_HIGH", "15") or 15)
    update_publish_queue_priority(job_id, high, source="pin")
    _notify()
    return {"ok": True, "job_id": job_id, "priority": high, "pinned": True}


def reschedule_job(*, job_id: str, scheduled_ts: int, org_id: str = "") -> dict[str, Any]:
    from core.storage import get_publish_queue_job, update_publish_queue_schedule
    from services.tenant import assert_org_access

    job = get_publish_queue_job(job_id)
    if not job:
        return {"ok": False, "error": "job_not_found"}
    ok, err = assert_org_access(job, org_id)
    if not ok:
        return {"ok": False, "error": err}
    if str(job.get("status") or "") != "queued":
        return {"ok": False, "error": "job_not_queued"}

    ts = max(int(time.time()), int(scheduled_ts))
    update_publish_queue_schedule(job_id, ts, {"rescheduled": True})
    _notify()
    return {"ok": True, "job_id": job_id, "scheduled_ts": ts}


def cancel_queued_job(*, job_id: str, org_id: str = "", reason: str = "") -> dict[str, Any]:
    from core.storage import get_publish_queue_job, update_publish_queue_status
    from services.tenant import assert_org_access

    job = get_publish_queue_job(job_id)
    if not job:
        return {"ok": False, "error": "job_not_found"}
    ok, err = assert_org_access(job, org_id)
    if not ok:
        return {"ok": False, "error": err}
    if str(job.get("status") or "") != "queued":
        return {"ok": False, "error": "job_not_queued", "status": job.get("status")}

    payload = dict(job.get("payload") or {})
    payload["cancel_reason"] = (reason or "manual_cancel")[:200]
    update_publish_queue_status(job_id, "cancelled", payload)
    _notify()
    return {"ok": True, "job_id": job_id, "status": "cancelled"}


def _notify() -> None:
    try:
        from services.dashboard_hub import notify_dashboard_update

        notify_dashboard_update(reason="publish_queue_ops")
    except Exception:
        pass
