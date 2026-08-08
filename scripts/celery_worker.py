#!/usr/bin/env python
"""启动 Celery Worker 进程。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()

raise SystemExit(
    subprocess.call(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "infra.task_queue.celery_app",
            "worker",
            "--loglevel=info",
            *sys.argv[1:],
        ],
        cwd=str(ROOT),
    )
)
