#!/usr/bin/env python
"""手动/定时投流报表轮询（可配合 Windows 任务计划 / cron）。"""
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


def main() -> int:
    parser = argparse.ArgumentParser(description="投流报表轮询")
    parser.add_argument("--daemon", action="store_true", help="后台循环轮询")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    if args.daemon:
        import os

        os.environ["AD_POLL_ENABLED"] = "1"
        from services.ad_scheduler import start_background_poller
        import time

        start_background_poller()
        print("ad poller started, Ctrl+C to stop", file=sys.stderr)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            from services.ad_scheduler import stop_background_poller

            stop_background_poller()
        return 0

    from services.ad_scheduler import poll_all_campaigns

    out = poll_all_campaigns(days=args.days)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
