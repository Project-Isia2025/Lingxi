"""Runbook 失败项飞书/Webhook 告警。"""
from __future__ import annotations

import os
import time
from typing import Any


def runbook_alert_enabled() -> bool:
    return os.environ.get("RUNBOOK_ALERT_ENABLED", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def runbook_alert_min_failures() -> int:
    try:
        return max(1, int(os.environ.get("RUNBOOK_ALERT_MIN_FAILURES", "1")))
    except ValueError:
        return 1


def extract_runbook_failures(runbook: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for step in runbook.get("steps") or []:
        if step.get("skipped"):
            continue
        if not step.get("ok"):
            out.append({
                "step": step.get("step"),
                "detail": step.get("detail") or "",
            })
    return out


def build_runbook_alert_payload(
    *,
    runbook: dict[str, Any],
    org_id: str = "",
    platform: str = "douyin",
) -> dict[str, Any]:
    failures = extract_runbook_failures(runbook)
    alerts = [
        {
            "level": "error" if i == 0 else "warning",
            "type": "runbook_step_failed",
            "message": f"{f.get('step')}: {f.get('detail') or 'failed'}",
        }
        for i, f in enumerate(failures)
    ]
    score = runbook.get("passed"), runbook.get("total")
    return {
        "event": "runbook_alert",
        "run_id": f"runbook-{org_id or 'default'}-{int(time.time())}",
        "org_id": org_id or "",
        "platform": platform,
        "alerts": alerts,
        "extra": {
            "passed": runbook.get("passed"),
            "total": runbook.get("total"),
            "live": runbook.get("live"),
            "failures": failures,
            "score": f"{score[0]}/{score[1]}",
        },
    }


def should_dispatch_runbook_alert(runbook: dict[str, Any]) -> bool:
    if not runbook_alert_enabled():
        return False
    failures = extract_runbook_failures(runbook)
    if runbook.get("ok"):
        return False
    return len(failures) >= runbook_alert_min_failures()


def dispatch_runbook_alert(
    *,
    runbook: dict[str, Any],
    org_id: str = "",
    platform: str = "douyin",
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    if not force and not should_dispatch_runbook_alert(runbook):
        return {
            "ok": True,
            "sent": False,
            "reason": "no_alert_needed" if runbook.get("ok") else "below_threshold",
        }

    payload = build_runbook_alert_payload(runbook=runbook, org_id=org_id, platform=platform)
    if dry_run:
        return {"ok": True, "sent": False, "dry_run": True, "payload": payload}

    from services.org_webhook_config import send_org_webhook

    result = send_org_webhook(org_id=org_id, kind="runbook", payload=payload)
    try:
        from core.storage import metrics_record

        metrics_record(
            run_id=payload.get("run_id") or "runbook",
            event_type="runbook_alert",
            value=float(len(payload.get("alerts") or [])),
            payload={"org_id": org_id, "webhook": result, "failures": payload.get("extra", {}).get("failures")},
        )
    except Exception:
        pass
    return {
        "ok": bool(result.get("ok")),
        "sent": bool(result.get("ok")),
        "webhook": result,
        "payload": payload,
    }
