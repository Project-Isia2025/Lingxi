#!/usr/bin/env python
"""完播监控 + 下架 + 重剪 E2E 验收（进程内 dry-run，无需真实创作者中心）。

用法:
  python scripts/acceptance_monitor_e2e.py
  python scripts/acceptance_monitor_e2e.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()


def run_monitor_e2e(*, run_id: str = "") -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from api_server import app
    from core.storage import init_storage, list_due_post_monitors, list_post_monitors
    from services.monitor_readiness import monitor_readiness_status
    from services.post_publish_monitor import poll_monitor, schedule_monitor

    client = TestClient(app)
    rid = run_id or f"mon-e2e-{uuid.uuid4().hex[:8]}"
    steps: list[dict[str, Any]] = []
    post_url = "https://www.douyin.com/video/7123456789012345678"

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "monitor_e2e.db"
        env_patch = {
            "POST_PUBLISH_MONITOR_ENABLED": "1",
            "TAKEDOWN_ENABLED": "0",
            "COMPLETION_RATE_MIN": "0.30",
            "CTR_MIN": "0.008",
        }

        with patch("core.storage.DB_PATH", db), patch.dict("os.environ", env_patch):
            init_storage()

            ready = monitor_readiness_status(platform="douyin")
            steps.append({
                "step": "monitor_readiness",
                "ok": ready.get("ok") and ready.get("monitor_enabled"),
                "result": ready,
            })

            with patch("services.post_publish_monitor.monitor_delay_sec", return_value=0):
                sched = schedule_monitor(
                    run_id=rid,
                    platform="douyin",
                    post_url=post_url,
                    keyword="测试",
                    script="监控 E2E 测试脚本",
                )
            steps.append({
                "step": "schedule_monitor",
                "ok": bool(sched.get("ok")),
                "result": sched,
            })

            due = list_due_post_monitors(limit=5)
            steps.append({
                "step": "monitor_due",
                "ok": len(due) >= 1,
                "result": {"count": len(due), "monitor_id": due[0].get("monitor_id") if due else ""},
            })

            low_metrics = {
                "ok": True,
                "run_id": rid,
                "platform": "douyin",
                "post_url": post_url,
                "completion_rate": 0.12,
                "ctr": 0.003,
                "source": "mock_e2e",
            }
            with patch("services.post_publish_monitor.fetch_post_metrics", return_value=low_metrics):
                low_result = poll_monitor(due[0])
            takedown = low_result.get("takedown") or {}
            steps.append({
                "step": "poll_low_takedown_reedit",
                "ok": (
                    low_result.get("low_performance")
                    and bool(takedown.get("dry_run"))
                    and bool(low_result.get("reedit", {}).get("reedit"))
                ),
                "result": low_result,
            })

            rid2 = f"{rid}-ok"
            with patch("services.post_publish_monitor.monitor_delay_sec", return_value=0):
                sched2 = schedule_monitor(
                    run_id=rid2,
                    platform="douyin",
                    post_url=post_url,
                )
            due2 = list_due_post_monitors(limit=5)
            target = next((m for m in due2 if m.get("run_id") == rid2), due2[0] if due2 else None)

            good_metrics = {
                "ok": True,
                "run_id": rid2,
                "platform": "douyin",
                "post_url": post_url,
                "completion_rate": 0.55,
                "ctr": 0.025,
                "source": "mock_e2e",
            }
            with patch("services.post_publish_monitor.fetch_post_metrics", return_value=good_metrics):
                good_result = poll_monitor(target) if target else {"ok": False}

            ok_rows = list_post_monitors(status="ok", limit=10)
            steps.append({
                "step": "poll_good_status",
                "ok": bool(good_result.get("ok")) and not good_result.get("low_performance"),
                "result": {"poll": good_result, "ok_count": len(ok_rows), "sched2": sched2},
            })

            r = client.get("/api/monitor/readiness")
            steps.append({
                "step": "readiness_api",
                "ok": r.status_code == 200 and r.json().get("monitor_enabled"),
                "result": r.json(),
            })

            r2 = client.get("/api/monitor/post-publish/status")
            steps.append({
                "step": "worker_status_api",
                "ok": r2.status_code == 200 and r2.json().get("ok"),
                "result": r2.json(),
            })

            r3 = client.post("/api/monitor/post-publish/poll?limit=3")
            steps.append({
                "step": "poll_api",
                "ok": r3.status_code == 200 and r3.json().get("ok") is not False,
                "result": r3.json(),
            })

    passed = sum(1 for s in steps if s.get("ok"))
    return {
        "ok": passed == len(steps),
        "passed": passed,
        "total": len(steps),
        "run_id": rid,
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="完播监控 E2E 验收")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_monitor_e2e()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"监控 E2E: {report.get('passed', 0)}/{report.get('total', 0)} 通过 | run={report.get('run_id')}")
        for step in report.get("steps") or []:
            mark = "OK" if step.get("ok") else "FAIL"
            print(f"  [{mark}] {step['step']}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
