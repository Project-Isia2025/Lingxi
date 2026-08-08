#!/usr/bin/env python
"""发布 → 完播监控 live 链路验收。

用法:
  python scripts/acceptance_publish_monitor_live.py
  python scripts/acceptance_publish_monitor_live.py --live --platform douyin
  python scripts/acceptance_publish_monitor_live.py --json
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


def run_publish_monitor_live(*, live: bool = False, platform: str = "douyin") -> dict:
    from services.publish_monitor_chain import run_publish_monitor_chain

    return run_publish_monitor_chain(live=live, platform=platform)


def main() -> int:
    parser = argparse.ArgumentParser(description="发布→监控 live 链路验收")
    parser.add_argument("--live", action="store_true", help="登录态就绪时真实上传页探测")
    parser.add_argument("--platform", default="douyin")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_publish_monitor_live(live=args.live, platform=args.platform)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"发布→监控: {report.get('passed', 0)}/{report.get('total', 0)} 通过 | "
            f"live={args.live} run={report.get('run_id')}"
        )
        for step in report.get("steps") or []:
            mark = "OK" if step.get("ok") else "FAIL"
            skip = " (skip)" if step.get("skipped") else ""
            print(f"  [{mark}] {step['step']}{skip}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
