"""历史任务清理 — 审核 / 工作流 / 决策的删除与自动 purge。"""
from __future__ import annotations

import os
from typing import Any

_COMPLETED_RUN_STATUSES = ("completed", "cancelled", "failed")
_RESOLVED_REVIEW_STATUSES = ("approved", "rejected")


def _as_bool(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def review_auto_delete_on_resolve() -> bool:
    return _as_bool("REVIEW_AUTO_DELETE_ON_RESOLVE", "1")


def review_retention_sec() -> int:
    try:
        return max(3600, int(os.environ.get("REVIEW_RETENTION_SEC", "604800")))
    except ValueError:
        return 604800


def workflow_run_retention_sec() -> int:
    try:
        return max(3600, int(os.environ.get("WORKFLOW_RUN_RETENTION_SEC", "2592000")))
    except ValueError:
        return 2592000


def workflow_decision_retention_sec() -> int:
    try:
        return max(3600, int(os.environ.get("WORKFLOW_DECISION_RETENTION_SEC", "604800")))
    except ValueError:
        return 604800


def clear_all_completed_runs() -> dict[str, Any]:
    from orchestrator.workflow_store import delete_all_runs_with_status, list_runs

    before = len([r for r in list_runs(limit=500) if str(r.get("status") or "") in _COMPLETED_RUN_STATUSES])
    result = delete_all_runs_with_status(statuses=_COMPLETED_RUN_STATUSES)
    after = len([r for r in list_runs(limit=500) if str(r.get("status") or "") in _COMPLETED_RUN_STATUSES])
    return {
        "ok": True,
        "deleted": int(result.get("deleted") or 0),
        "before_count": before,
        "after_count": after,
    }


def purge_all_completed_tasks() -> dict[str, Any]:
    from core.storage.review import purge_reviews
    from orchestrator.workflow_store import purge_runs
    from services.workflow_decisions import purge_resolved_decisions

    review = purge_reviews(statuses=_RESOLVED_REVIEW_STATUSES, older_than_sec=review_retention_sec())
    runs = purge_runs(statuses=_COMPLETED_RUN_STATUSES, older_than_sec=workflow_run_retention_sec())
    decisions = purge_resolved_decisions(older_than_sec=workflow_decision_retention_sec())
    total = int(review.get("deleted") or 0) + int(runs.get("deleted") or 0) + int(decisions.get("deleted") or 0)
    return {
        "ok": True,
        "deleted_total": total,
        "review": review,
        "workflow_runs": runs,
        "workflow_decisions": decisions,
    }


def delete_review_item(review_id: str, *, allow_pending: bool = True) -> dict[str, Any]:
    from core.storage import delete_review, get_review_item

    item = get_review_item(review_id)
    if not item:
        return {"ok": False, "error": "review_not_found"}
    status = str(item.get("status") or "")
    if status == "pending_review" and not allow_pending:
        return {"ok": False, "error": "pending_review_cannot_delete"}
    if delete_review(review_id):
        return {"ok": True, "review_id": review_id, "status": status}
    return {"ok": False, "error": "delete_failed"}


def clear_all_pending_reviews() -> dict[str, Any]:
    from core.storage.review import delete_all_pending_reviews, list_review_queue

    before = len(list_review_queue(status="pending_review", limit=500))
    result = delete_all_pending_reviews()
    after = len(list_review_queue(status="pending_review", limit=500))
    return {
        "ok": True,
        "deleted": int(result.get("deleted") or 0),
        "before_count": before,
        "after_count": after,
    }


def delete_workflow_run(run_id: str, *, allow_active: bool = False) -> dict[str, Any]:
    from orchestrator.orchestrator_agent import _ACTIVE
    from orchestrator.workflow_store import delete_run, load_run

    data = load_run(run_id)
    if not data:
        return {"ok": False, "error": "run_not_found"}
    status = str(data.get("status") or "")
    if run_id in _ACTIVE and not allow_active:
        return {"ok": False, "error": "run_still_active"}
    if status not in _COMPLETED_RUN_STATUSES and not allow_active:
        return {"ok": False, "error": "run_not_finished", "status": status}
    if delete_run(run_id):
        return {"ok": True, "run_id": run_id, "status": status}
    return {"ok": False, "error": "delete_failed"}


def delete_workflow_decision(decision_id: str) -> dict[str, Any]:
    from services.workflow_decisions import delete_decision, get_decision

    item = get_decision(decision_id)
    if not item:
        return {"ok": False, "error": "decision_not_found"}
    if delete_decision(decision_id):
        return {"ok": True, "decision_id": decision_id, "status": item.get("status")}
    return {"ok": False, "error": "delete_failed"}


def cleanup_status() -> dict[str, Any]:
    from core.storage import list_review_queue
    from orchestrator.workflow_store import list_runs

    pending_reviews = list_review_queue(status="pending_review", limit=200)
    runs = list_runs(limit=200)
    completed_runs = [r for r in runs if str(r.get("status") or "") in _COMPLETED_RUN_STATUSES]
    return {
        "ok": True,
        "auto_delete_on_resolve": review_auto_delete_on_resolve(),
        "retention_sec": {
            "review": review_retention_sec(),
            "workflow_run": workflow_run_retention_sec(),
            "workflow_decision": workflow_decision_retention_sec(),
        },
        "counts": {
            "pending_reviews": len(pending_reviews),
            "completed_runs": len(completed_runs),
        },
    }
