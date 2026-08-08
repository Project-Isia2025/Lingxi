"""发布 → 完播监控链路（dry-run / 可选 live 探测）。"""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch


def run_publish_monitor_chain(
    *,
    live: bool = False,
    platform: str = "douyin",
    run_id: str = "",
) -> dict[str, Any]:
    from core.storage import init_storage, list_due_post_monitors, list_post_monitors
    from services.post_publish_monitor import poll_monitor, schedule_monitor
    from services.publish.scheduler import schedule_publish

    rid = run_id or f"pub-mon-{uuid.uuid4().hex[:8]}"
    plat = platform.strip().lower()
    if plat == "xhs":
        plat = "xiaohongshu"
    post_url = "https://www.douyin.com/video/7123456789012345678"
    steps: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "pub_mon_chain.db"
        video = Path(td) / "chain.mp4"
        video.write_bytes(b"\x00" * 1500)

        with patch("core.storage.DB_PATH", db):
            init_storage()

            queued = schedule_publish(
                platform=plat,
                video_path=str(video),
                script="发布→监控链路验收",
                title="链路验收",
                run_id=rid,
            )
            steps.append({
                "step": "enqueue_publish",
                "ok": bool(queued.get("ok")),
                "result": queued,
            })

            with patch("services.post_publish_monitor.monitor_delay_sec", return_value=0):
                mon = schedule_monitor(
                    run_id=rid,
                    platform=plat,
                    post_url=post_url,
                    job_id=str(queued.get("job_id") or ""),
                    keyword="链路",
                    script="监控验收",
                )
            steps.append({
                "step": "schedule_monitor",
                "ok": bool(mon.get("ok")),
                "result": mon,
            })

            due = list_due_post_monitors(limit=3)
            steps.append({
                "step": "monitor_due",
                "ok": len(due) >= 1,
                "result": {"count": len(due)},
            })

            metrics = {
                "ok": True,
                "run_id": rid,
                "platform": plat,
                "post_url": post_url,
                "completion_rate": 0.48,
                "ctr": 0.018,
                "source": "chain_mock",
            }
            with patch("services.post_publish_monitor.fetch_post_metrics", return_value=metrics):
                polled = poll_monitor(due[0]) if due else {"ok": False}
            steps.append({
                "step": "poll_monitor_ok",
                "ok": bool(polled.get("ok")) and not polled.get("low_performance"),
                "result": polled,
            })

            ok_rows = list_post_monitors(status="ok", limit=5)
            steps.append({
                "step": "monitor_status_ok",
                "ok": len(ok_rows) >= 1,
                "result": {"ok_count": len(ok_rows)},
            })

            if live:
                from services.publish_readiness import platform_readiness
                from services.publish_smoke import probe_publish_upload

                ready = platform_readiness(plat)
                if ready.get("ready"):
                    probe = probe_publish_upload(platform=plat, headed=False)
                    steps.append({
                        "step": "live_upload_probe",
                        "ok": bool(probe.get("ok")),
                        "result": probe,
                    })
                else:
                    steps.append({
                        "step": "live_upload_probe",
                        "ok": True,
                        "skipped": True,
                        "result": ready,
                    })
            else:
                steps.append({
                    "step": "live_upload_probe",
                    "ok": True,
                    "skipped": True,
                    "result": {"hint": "追加 --live 执行真实上传页探测"},
                })

    passed = sum(1 for s in steps if s.get("ok"))
    required = [s for s in steps if not s.get("skipped")]
    req_passed = sum(1 for s in required if s.get("ok"))
    return {
        "ok": req_passed == len(required),
        "passed": passed,
        "total": len(steps),
        "live": live,
        "platform": plat,
        "run_id": rid,
        "steps": steps,
    }
