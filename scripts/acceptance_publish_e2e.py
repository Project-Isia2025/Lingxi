#!/usr/bin/env python
"""Playwright 创作者中心发布联调验收（dry-run，无需真实上传）。

用法:
  python scripts/acceptance_publish_e2e.py
  python scripts/acceptance_publish_e2e.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()


def run_publish_e2e() -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from api_server import app
    from services.publish.common import build_metadata, validate_video_path
    from services.publish_readiness import all_publish_readiness, dry_run_publish_check
    from services.publish.router import supported_platforms
    from services.tunnel import tunnel_status

    client = TestClient(app)
    steps: list[dict[str, Any]] = []

    readiness = all_publish_readiness()
    steps.append({"step": "publish_readiness", "ok": readiness.get("ok"), "result": readiness})

    tunnel = tunnel_status()
    steps.append({"step": "tunnel_status", "ok": tunnel.get("ok"), "result": tunnel})

    with tempfile.TemporaryDirectory() as td:
        video = Path(td) / "demo_publish.mp4"
        video.write_bytes(b"\x00" * 1200)
        script = "A款面膜15秒口播验收测试。"

        ok_path, _ = validate_video_path(str(video))
        meta = build_metadata(script=script, title="验收测试")
        steps.append({
            "step": "metadata_build",
            "ok": bool(meta.get("title")) and ok_path,
            "result": {"title": meta.get("title"), "tags": meta.get("tags")},
        })

        for plat in supported_platforms():
            out = dry_run_publish_check(platform=plat, video_path=str(video), script=script, title="验收")
            steps.append({
                "step": f"dry_run_{plat}",
                "ok": out.get("ok"),
                "result": {"platform": plat, "dry_run": True},
            })

        r = client.post(
            "/api/publish/run",
            json={
                "platform": "douyin",
                "video_path": str(video),
                "script": script,
                "title": "验收",
                "dry_run": True,
                "run_id": f"pub-e2e-{uuid.uuid4().hex[:8]}",
            },
        )
        body = r.json()
        steps.append({
            "step": "api_publish_dry_run",
            "ok": r.status_code == 200 and body.get("ok"),
            "result": body,
        })

        r = client.get("/api/publish/readiness")
        steps.append({
            "step": "api_readiness",
            "ok": r.status_code == 200 and r.json().get("ok"),
            "result": r.json(),
        })

        r = client.get("/api/tunnel/status")
        steps.append({
            "step": "api_tunnel_status",
            "ok": r.status_code == 200 and r.json().get("ok"),
            "result": r.json(),
        })

    passed = sum(1 for s in steps if s.get("ok"))
    return {
        "ok": passed == len(steps),
        "passed": passed,
        "total": len(steps),
        "ready_platforms": readiness.get("ready") or [],
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Playwright 发布联调验收（dry-run）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_publish_e2e()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"发布联调 E2E: {report.get('passed', 0)}/{report.get('total', 0)} 通过")
        if report.get("ready_platforms"):
            print(f"  就绪平台: {', '.join(report['ready_platforms'])}")
        for step in report.get("steps") or []:
            mark = "OK" if step.get("ok") else "FAIL"
            print(f"  [{mark}] {step['step']}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
