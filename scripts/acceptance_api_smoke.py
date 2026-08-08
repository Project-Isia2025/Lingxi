#!/usr/bin/env python
"""API 进程内烟测（TestClient，无需启动 uvicorn）。

用法:
  python scripts/acceptance_api_smoke.py
  python scripts/acceptance_api_smoke.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()


def _probe(name: str, fn: Callable[[], tuple[int, dict[str, Any]]]) -> dict[str, Any]:
    try:
        status, body = fn()
        ok = 200 <= status < 300 and bool(body.get("ok", True))
        return {"step": name, "ok": ok, "status": status, "body_keys": sorted(body.keys())[:8]}
    except Exception as exc:
        return {"step": name, "ok": False, "error": str(exc)[:300]}


def run_api_smoke() -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from api_server import app

    client = TestClient(app)
    steps: list[dict[str, Any]] = []

    def get(path: str) -> tuple[int, dict[str, Any]]:
        r = client.get(path)
        try:
            body = r.json()
        except Exception:
            body = {"ok": False, "raw": r.text[:200]}
        if not isinstance(body, dict):
            body = {"ok": True, "data": body}
        return r.status_code, body

    endpoints = [
        ("health", "/api/health"),
        ("root", "/"),
        ("orchestrator_status", "/api/orchestrator/status"),
        ("inventory", "/api/inventory"),
        ("publish_accounts", "/api/publish/accounts"),
        ("video_providers", "/api/video/providers"),
        ("video_providers_status", "/api/video/providers/status"),
        ("review_status", "/api/review/status"),
        ("review_feishu_status", "/api/review/feishu/status"),
        ("storage_status", "/api/storage/status"),
        ("publish_readiness", "/api/publish/readiness"),
        ("tunnel_status", "/api/tunnel/status"),
        ("docker_compose_status", "/api/docker/compose/status"),
        ("deploy_status", "/api/deploy/status"),
        ("deploy_helm_status", "/api/deploy/helm/status"),
        ("monitor_readiness", "/api/monitor/readiness"),
        ("post_publish_monitor_status", "/api/monitor/post-publish/status"),
        ("runtime_status", "/api/runtime/status"),
        ("runtime_runbook", "/api/runtime/runbook?live=false"),
        ("runtime_dashboard", "/api/dashboard/runtime?platform=douyin"),
        ("org_catalog", "/api/orgs/catalog"),
        ("org_webhooks_status", "/api/orgs/webhooks/status"),
        ("runbook_alert_status", "/api/runtime/runbook/alert/status"),
        ("dashboard_ws_status", "/api/dashboard/ws/status"),
        ("publish_queue_dashboard", "/api/dashboard/publish-queue?limit=5"),
        ("perception_feed", "/api/dashboard/perception-feed?limit=5"),
        ("metrics_chart", "/api/dashboard/metrics-chart?days=7"),
    ]
    for name, path in endpoints:
        steps.append(_probe(name, lambda p=path: get(p)))

    passed = sum(1 for s in steps if s.get("ok"))
    return {
        "ok": passed == len(steps),
        "passed": passed,
        "total": len(steps),
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="API 进程内烟测")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_api_smoke()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"API 烟测: {report['passed']}/{report['total']} 通过")
        for step in report["steps"]:
            mark = "OK" if step.get("ok") else "FAIL"
            extra = step.get("status") or step.get("error") or ""
            print(f"  [{mark}] {step['step']} {extra}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
