#!/usr/bin/env python
"""Playwright 上传页 smoke 探测（需登录态；默认仅检查，--live-probe 才打开浏览器）。

用法:
  python scripts/acceptance_publish_smoke.py
  python scripts/acceptance_publish_smoke.py --live-probe --platform douyin --headed
  python scripts/acceptance_publish_smoke.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()


def run_publish_smoke_acceptance(
    *,
    platform: str = "douyin",
    live_probe: bool = False,
    headed: bool = False,
    submit: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    from services.compose_profiles import compose_status
    from services.publish_readiness import all_publish_readiness, platform_readiness
    from services.publish_smoke import probe_publish_upload
    from services.publish.playwright_util import playwright_installed

    steps: list[dict[str, Any]] = []
    readiness = all_publish_readiness()
    steps.append({"step": "publish_readiness", "ok": readiness.get("ok"), "result": readiness})

    plat_ready = platform_readiness(platform)
    steps.append({
        "step": f"platform_{platform}_ready",
        "ok": True,
        "skipped": not plat_ready.get("ready"),
        "result": plat_ready,
    })

    steps.append({
        "step": "compose_full_stack",
        "ok": compose_status().get("full_stack_ready"),
        "result": compose_status(),
    })

    if not live_probe and not submit:
        steps.append({
            "step": "live_probe",
            "ok": True,
            "skipped": True,
            "result": {"hint": "追加 --live-probe 探测或 --submit --confirm 真实发布"},
        })
    elif submit and not confirm:
        out = probe_publish_upload(platform=platform, submit=True, confirm=False)
        steps.append({"step": "submit_guard", "ok": out.get("error") == "submit_requires_confirm", "result": out})
    elif not plat_ready.get("ready"):
        steps.append({
            "step": "live_probe",
            "ok": True,
            "skipped": True,
            "result": {"hint": "登录态未就绪，跳过；运行 export_storage_wizard --export douyin_creator"},
        })
    elif not playwright_installed():
        steps.append({"step": "live_probe", "ok": False, "error": "playwright_not_installed"})
    else:
        out = probe_publish_upload(
            platform=platform,
            headed=headed if headed else None,
            submit=submit,
            confirm=confirm,
        )
        steps.append({"step": "live_probe" if not submit else "live_submit", "ok": out.get("ok"), "result": out})

    required = [s for s in steps if not s.get("skipped")]
    passed = sum(1 for s in required if s.get("ok"))
    return {
        "ok": all(s.get("ok") for s in required),
        "passed": passed,
        "total": len(required),
        "live_probe": live_probe,
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Playwright 上传页 smoke 验收")
    parser.add_argument("--platform", default="douyin")
    parser.add_argument("--live-probe", action="store_true", help="真实打开浏览器探测（需登录态）")
    parser.add_argument("--submit", action="store_true", help="探测后真实点击发布（需 --confirm）")
    parser.add_argument("--confirm", action="store_true", help="确认真实发布（将上传至创作者中心）")
    parser.add_argument("--headed", action="store_true", help="有界面模式（调试用）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_publish_smoke_acceptance(
        platform=args.platform,
        live_probe=args.live_probe or args.submit,
        headed=args.headed,
        submit=args.submit,
        confirm=args.confirm,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        mode = "LIVE" if args.live_probe else "CHECK-ONLY"
        print(f"发布 Smoke [{mode}]: {report.get('passed', 0)}/{report.get('total', 0)} 通过")
        for step in report.get("steps") or []:
            mark = "OK" if step.get("ok") else ("SKIP" if step.get("skipped") else "FAIL")
            print(f"  [{mark}] {step['step']}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
