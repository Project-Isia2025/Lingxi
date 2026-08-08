"""发布队列失败重试策略。"""
from __future__ import annotations

import os
import time
from typing import Any

from core.storage import get_publish_queue_job, requeue_publish_job, update_publish_queue_status
from services.publish_feedback import apply_publish_failure_feedback

NON_RETRIABLE_ERRORS = frozenset(
    {
        "storage_state_missing",
        "creator_login_required",
        "publish_disabled",
        "unsupported_platform",
        "video_not_found",
    }
)


def max_retries() -> int:
    try:
        return max(0, int(os.environ.get("PUBLISH_QUEUE_MAX_RETRIES", "3")))
    except ValueError:
        return 3


def retry_delay_sec() -> int:
    try:
        return max(60, int(os.environ.get("PUBLISH_QUEUE_RETRY_DELAY_SEC", "600")))
    except ValueError:
        return 600


def retry_enabled() -> bool:
    return os.environ.get("PUBLISH_QUEUE_RETRY_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def is_retriable_error(error: str) -> bool:
    err = str(error or "").strip().lower()
    if not err:
        return True
    for blocked in NON_RETRIABLE_ERRORS:
        if blocked in err:
            return False
    return True


def handle_publish_failure(
    job: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """处理发布失败：重试入队或标记 failed。"""
    job_id = str(job.get("job_id") or "")
    error = str(result.get("error") or result.get("message") or "publish_failed")
    run_id = str(job.get("run_id") or "")
    platform = str(job.get("platform") or "")

    row = get_publish_queue_job(job_id) or {}
    payload = dict(row.get("payload") or {})
    retry_count = int(payload.get("retry_count") or 0)

    apply_publish_failure_feedback(
        platform=platform,
        error=error,
        run_id=run_id,
        job_id=job_id,
        retry_count=retry_count + 1,
    )

    if not retry_enabled() or not is_retriable_error(error):
        update_publish_queue_status(job_id, "failed", {**result, "retry_count": retry_count, "final_error": error})
        return {"job_id": job_id, "status": "failed", "retries": retry_count, "error": error}

    next_retry = retry_count + 1
    if next_retry > max_retries():
        update_publish_queue_status(
            job_id,
            "failed",
            {**result, "retry_count": retry_count, "final_error": error, "exhausted_retries": True},
        )
        return {"job_id": job_id, "status": "failed", "retries": retry_count, "error": error, "exhausted": True}

    delay = retry_delay_sec() * next_retry
    scheduled_ts = int(time.time()) + delay
    requeue_publish_job(
        job_id=job_id,
        retry_count=next_retry,
        scheduled_ts=scheduled_ts,
        last_error=error,
        extra={"last_result": result},
    )
    _notify_retry("publish_retry")
    return {
        "job_id": job_id,
        "status": "queued",
        "retry_count": next_retry,
        "scheduled_ts": scheduled_ts,
        "error": error,
        "retry_in_sec": delay,
    }


def _notify_retry(reason: str) -> None:
    try:
        from services.dashboard_hub import notify_dashboard_update

        notify_dashboard_update(reason=reason)
    except Exception:
        pass
