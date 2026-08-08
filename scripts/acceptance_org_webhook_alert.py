#!/usr/bin/env python
"""多 org Webhook + Runbook 告警验收。

用法:
  python scripts/acceptance_org_webhook_alert.py
  python scripts/acceptance_org_webhook_alert.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()


def run_org_webhook_acceptance() -> dict:
    from fastapi.testclient import TestClient
    from unittest.mock import patch

    from api_server import app
    from services.live_runbook import build_live_runbook
    from services.org_webhook_config import resolve_webhook, upsert_org_config
    from services.runbook_alert import dispatch_runbook_alert, runbook_alert_enabled

    steps: list[dict] = []

    steps.append({
        "step": "runbook_alert_enabled",
        "ok": runbook_alert_enabled(),
        "result": {},
    })

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "org_webhooks.json"
        with patch("services.org_webhook_config.org_webhooks_path", return_value=path):
            upsert_org_config(
                "accept-org",
                {
                    "label": "验收租户",
                    "review_webhook_url": "https://example.com/review",
                    "runbook_webhook_url": "https://example.com/runbook",
                    "review_base_url": "https://example.com",
                },
            )
            steps.append({
                "step": "org_webhook_resolve",
                "ok": resolve_webhook("accept-org", "runbook") == "https://example.com/runbook",
                "result": {},
            })

            runbook = build_live_runbook(live=False, org_id="accept-org")
            alert = dispatch_runbook_alert(runbook=runbook, org_id="accept-org", dry_run=True, force=True)
            steps.append({
                "step": "runbook_alert_dry_run",
                "ok": alert.get("dry_run") and bool(alert.get("payload")),
                "result": {"sent": alert.get("sent")},
            })

    client = TestClient(app)
    r = client.get("/api/orgs/webhooks/status")
    steps.append({"step": "webhooks_status_api", "ok": r.status_code == 200 and r.json().get("ok"), "result": {}})

    r2 = client.post("/api/orgs/accept-org/webhooks", json={"label": "API租户", "enabled": True})
    steps.append({"step": "upsert_org_api", "ok": r2.status_code == 200 and r2.json().get("ok"), "result": r2.json()})

    r3 = client.post("/api/runtime/runbook/alert?dry_run=1&org_id=accept-org")
    steps.append({"step": "runbook_alert_api", "ok": r3.status_code == 200 and r3.json().get("ok"), "result": {}})

    passed = sum(1 for s in steps if s.get("ok"))
    return {"ok": passed == len(steps), "passed": passed, "total": len(steps), "steps": steps}


def main() -> int:
    parser = argparse.ArgumentParser(description="org Webhook + Runbook 告警验收")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_org_webhook_acceptance()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Org Webhook+告警: {report.get('passed', 0)}/{report.get('total', 0)} 通过")
        for step in report.get("steps") or []:
            mark = "OK" if step.get("ok") else "FAIL"
            print(f"  [{mark}] {step['step']}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
