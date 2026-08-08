#!/usr/bin/env python
"""独立发布队列 Worker 守护进程。"""
from __future__ import annotations

import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()


def main() -> int:
    from services.publish_worker import start_background_worker

    if not start_background_worker():
        print("PUBLISH_QUEUE_ENABLED=0，Worker 未启动", file=sys.stderr)
        return 1

    def _stop(*_args) -> None:
        from services.publish_worker import stop_background_worker

        stop_background_worker()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    print("publish worker running…")
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    raise SystemExit(main())
