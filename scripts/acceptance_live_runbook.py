#!/usr/bin/env python
"""生产环境真实联调 Runbook 验收。

用法:
  python scripts/acceptance_live_runbook.py
  python scripts/acceptance_live_runbook.py --live --platform douyin
  python scripts/acceptance_live_runbook.py --json
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


def main() -> int:
    parser = argparse.ArgumentParser(description="生产联调 Runbook 验收")
    parser.add_argument("--live", action="store_true", help="含真实上传页探测（需登录态）")
    parser.add_argument("--platform", default="douyin")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    from services.live_runbook import build_live_runbook

    report = build_live_runbook(live=args.live, platform=args.platform)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"联调 Runbook: {report.get('passed', 0)}/{report.get('total', 0)} 通过 | "
            f"live={args.live} platform={args.platform}"
        )
        for step in report.get("steps") or []:
            mark = "OK" if step.get("ok") else "FAIL"
            skip = " (skip)" if step.get("skipped") else ""
            detail = step.get("detail") or ""
            print(f"  [{mark}] {step['step']}{skip}  {detail}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
