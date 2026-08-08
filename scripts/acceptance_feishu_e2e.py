#!/usr/bin/env python
"""飞书审核回调 E2E 验收（进程内模拟，无需真实 Webhook）。

用法:
  python scripts/acceptance_feishu_e2e.py
  python scripts/acceptance_feishu_e2e.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
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


def run_feishu_e2e(*, run_id: str = "") -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from api_server import app
    from core.storage import init_storage
    from services.feishu_review import review_token
    from services.feishu_review_status import feishu_review_status

    client = TestClient(app)
    rid = run_id or f"feishu-e2e-{uuid.uuid4().hex[:8]}"
    steps: list[dict[str, Any]] = []
    review_ids: list[str] = []

    steps.append({
        "step": "feishu_config",
        "ok": True,
        "result": feishu_review_status(),
    })

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "feishu_e2e.db"
        paths = []
        for i in range(3):
            p = Path(td) / f"slice_{i}.mp4"
            p.write_bytes(b"video")
            paths.append(str(p))

        env_patch = {
            "SLICE_APPROVE_MATRIX_PUBLISH": "0",
            "REVIEW_FEISHU_BATCH_CARD": "1",
            "REVIEW_FEISHU_USE_CALLBACK": "1",
        }

        with patch("core.storage.DB_PATH", db), patch(
            "services.feishu_review.send_review_card",
            return_value={"ok": True, "mock": True},
        ), patch.dict("os.environ", env_patch):
            init_storage()

            r = client.post("/api/review/callback", json={"challenge": "test-challenge-123"})
            body = r.json()
            steps.append({
                "step": "url_verification",
                "ok": r.status_code == 200 and body.get("challenge") == "test-challenge-123",
                "result": body,
            })

            from services.review_queue import submit_batch_for_review

            batch = submit_batch_for_review(
                run_id=rid,
                items=[
                    {
                        "video_path": paths[i],
                        "script": f"15秒切片脚本{i+1}",
                        "title": f"切片{i+1}",
                        "payload": {
                            "slice_id": f"S{i+1}",
                            "batch": "slice_drafts",
                            "platform": "douyin",
                            "keyword": "A面膜",
                            "auto_publish_on_approve": True,
                        },
                    }
                    for i in range(3)
                ],
                notify_feishu=True,
            )
            review_ids = list(batch.get("review_ids") or [])
            steps.append({
                "step": "submit_batch",
                "ok": bool(batch.get("ok")) and len(review_ids) == 3,
                "result": {"count": batch.get("count"), "batch_card": batch.get("batch_card")},
            })

            if len(review_ids) < 3:
                passed = sum(1 for s in steps if s.get("ok"))
                return {"ok": False, "passed": passed, "total": len(steps), "steps": steps, "run_id": rid}

            rid1, rid2 = review_ids[0], review_ids[1]
            r = client.post(
                "/api/review/callback",
                json={
                    "type": "card.action.trigger",
                    "action": {
                        "value": {
                            "action": "approve",
                            "review_id": rid1,
                            "token": review_token(rid1),
                            "slice_id": "S1",
                        },
                    },
                },
            )
            body = r.json()
            steps.append({
                "step": "callback_approve_slice",
                "ok": r.status_code == 200 and (body.get("toast") or {}).get("type") == "success",
                "result": body,
            })

            r = client.post(
                "/api/review/callback",
                json={
                    "action": {
                        "value": {
                            "action": "reject",
                            "review_id": rid2,
                            "token": review_token(rid2),
                            "reason": "验收测试打回：钩子不够痛",
                        },
                    },
                },
            )
            body = r.json()
            steps.append({
                "step": "callback_reject_slice",
                "ok": r.status_code == 200 and (body.get("toast") or {}).get("type") == "info",
                "result": body,
            })

            r = client.post(
                "/api/review/callback",
                json={
                    "action": {
                        "value": {
                            "action": "approve_all_slices",
                            "run_id": rid,
                            "token": review_token(f"batch-{rid}"),
                        },
                    },
                },
            )
            body = r.json()
            steps.append({
                "step": "callback_approve_all",
                "ok": r.status_code == 200 and (body.get("toast") or {}).get("type") == "success",
                "result": body,
            })

            r = client.get(f"/api/review/run/{rid}/slices")
            slice_body = r.json()
            approved = int(slice_body.get("approved") or 0)
            rejected = int(slice_body.get("rejected") or 0)
            steps.append({
                "step": "verify_slice_status",
                "ok": slice_body.get("ok") and approved >= 2 and rejected >= 1,
                "result": {"approved": approved, "rejected": rejected},
            })

            r = client.get("/api/dashboard/publish-queue?limit=20")
            queue_body = r.json()
            queued = int((queue_body.get("stats") or {}).get("total") or 0)
            steps.append({
                "step": "verify_publish_queue",
                "ok": r.status_code == 200 and queued >= 1,
                "result": {"queued_total": queued},
            })

    passed = sum(1 for s in steps if s.get("ok"))
    return {
        "ok": passed == len(steps),
        "passed": passed,
        "total": len(steps),
        "run_id": rid,
        "review_ids": review_ids,
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="飞书审核回调 E2E 验收")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_feishu_e2e(run_id=args.run_id)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"飞书回调 E2E: {report.get('passed', 0)}/{report.get('total', 0)} 通过  run={report.get('run_id')}")
        for step in report.get("steps") or []:
            mark = "OK" if step.get("ok") else "FAIL"
            print(f"  [{mark}] {step['step']}")
            if not step.get("ok"):
                print(f"       {step.get('error') or step.get('result')}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
