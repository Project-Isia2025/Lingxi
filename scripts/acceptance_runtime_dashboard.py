#!/usr/bin/env python
"""运维 Dashboard + E2E 联调指南验收。

用法:
  python scripts/acceptance_runtime_dashboard.py
  python scripts/acceptance_runtime_dashboard.py --json
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


def run_runtime_dashboard_acceptance() -> dict:
    from fastapi.testclient import TestClient

    from api_server import app
    from services.runtime_dashboard import build_runtime_dashboard

    steps: list[dict] = []

    dash = build_runtime_dashboard(platform="douyin")
    steps.append({
        "step": "build_runtime_dashboard",
        "ok": dash.get("ok") and len(dash.get("cards") or []) >= 5,
        "result": {"cards": len(dash.get("cards") or []), "guide_phases": len(dash.get("guide") or [])},
    })

    steps.append({
        "step": "runbook_checklist",
        "ok": len(dash.get("runbook_checklist") or []) >= 7,
        "result": {"count": len(dash.get("runbook_checklist") or [])},
    })

    steps.append({
        "step": "e2e_guide",
        "ok": len(dash.get("guide") or []) >= 6,
        "result": {"phases": [p.get("phase") for p in (dash.get("guide") or [])[:3]]},
    })

    client = TestClient(app)
    r = client.get("/api/dashboard/runtime?platform=douyin")
    steps.append({
        "step": "runtime_api",
        "ok": r.status_code == 200 and r.json().get("ok"),
        "result": {"status": r.status_code},
    })

    r2 = client.get("/dashboard/runtime")
    steps.append({
        "step": "runtime_page",
        "ok": r2.status_code == 200 and "运维中心" in (r2.text or ""),
        "result": {"status": r2.status_code, "len": len(r2.text or "")},
    })

    passed = sum(1 for s in steps if s.get("ok"))
    return {"ok": passed == len(steps), "passed": passed, "total": len(steps), "steps": steps}


def main() -> int:
    parser = argparse.ArgumentParser(description="运维 Dashboard 验收")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_runtime_dashboard_acceptance()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"运维 Dashboard: {report.get('passed', 0)}/{report.get('total', 0)} 通过")
        for step in report.get("steps") or []:
            mark = "OK" if step.get("ok") else "FAIL"
            print(f"  [{mark}] {step['step']}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
