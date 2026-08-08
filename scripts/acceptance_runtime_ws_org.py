#!/usr/bin/env python
"""运维 WebSocket + org 过滤验收。

用法:
  python scripts/acceptance_runtime_ws_org.py
  python scripts/acceptance_runtime_ws_org.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()


def run_runtime_ws_org_acceptance() -> dict:
    from fastapi.testclient import TestClient

    from api_server import app
    from services.dashboard_hub import runtime_connection_count
    from services.org_catalog import org_catalog_status
    from services.runtime_dashboard import build_runtime_dashboard

    steps: list[dict] = []

    catalog = org_catalog_status()
    steps.append({"step": "org_catalog", "ok": catalog.get("ok"), "result": catalog})

    dash = build_runtime_dashboard(platform="douyin", org_id="demo-org")
    steps.append({
        "step": "runtime_org_filter",
        "ok": dash.get("ok") and "org_queue" in dash,
        "result": {"org_id": dash.get("org_id"), "cards": len(dash.get("cards") or [])},
    })

    client = TestClient(app)
    r = client.get("/api/dashboard/runtime?platform=douyin&org_id=demo-org")
    steps.append({"step": "runtime_api_org", "ok": r.status_code == 200 and r.json().get("org_id") == "demo-org", "result": {}})

    r2 = client.get("/api/dashboard/ws/status")
    steps.append({
        "step": "ws_status_runtime",
        "ok": r2.status_code == 200 and "runtime_connections" in r2.json(),
        "result": r2.json(),
    })

    with client.websocket_connect("/ws/dashboard/runtime?platform=douyin") as ws:
        snap = ws.receive_json()
        steps.append({
            "step": "ws_snapshot",
            "ok": snap.get("channel") == "runtime" and snap.get("ok"),
            "result": {"event": snap.get("event")},
        })
        ws.send_text("refresh")
        upd = ws.receive_json()
        steps.append({
            "step": "ws_refresh",
            "ok": upd.get("event") == "update",
            "result": {"channel": upd.get("channel")},
        })

    steps.append({
        "step": "runtime_conn_count",
        "ok": runtime_connection_count() == 0,
        "result": {"count": runtime_connection_count()},
    })

    passed = sum(1 for s in steps if s.get("ok"))
    return {"ok": passed == len(steps), "passed": passed, "total": len(steps), "steps": steps}


def main() -> int:
    parser = argparse.ArgumentParser(description="运维 WS + org 验收")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_runtime_ws_org_acceptance()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"运维 WS+org: {report.get('passed', 0)}/{report.get('total', 0)} 通过")
        for step in report.get("steps") or []:
            mark = "OK" if step.get("ok") else "FAIL"
            print(f"  [{mark}] {step['step']}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
