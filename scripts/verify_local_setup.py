#!/usr/bin/env python
"""本地环境自检 — Redis / Celery / SQLite / 关键配置。

用法:
  python scripts/verify_local_setup.py
  python scripts/verify_local_setup.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()


def _check(name: str, ok: bool, detail: str = "", *, warn: bool = False) -> dict:
    level = "ok" if ok else ("warn" if warn else "fail")
    return {"name": name, "ok": ok, "level": level, "detail": detail}


def run_checks() -> dict:
    checks: list[dict] = []

    # SQLite
    try:
        from core.db import connect

        conn = connect()
        conn.execute("SELECT 1")
        conn.close()
        checks.append(_check("sqlite", True, str(bootstrap.project_root() / "data" / "matrix_agent.db")))
    except Exception as exc:
        checks.append(_check("sqlite", False, str(exc)[:200]))

    # Redis
    host = os.environ.get("REDIS_HOST", "localhost")
    port = int(os.environ.get("REDIS_PORT", "6379") or 6379)
    try:
        import redis

        client = redis.Redis(host=host, port=port, socket_connect_timeout=1.0, socket_timeout=1.0)
        pong = client.ping()
        checks.append(_check("redis", bool(pong), f"{host}:{port}"))
    except Exception as exc:
        backend = os.environ.get("WORKER_BACKEND", "celery")
        checks.append(
            _check(
                "redis",
                backend != "celery",
                f"{host}:{port} — {exc}"[:200],
                warn=backend == "thread",
            )
        )

    # Celery worker
    backend = (os.environ.get("WORKER_BACKEND") or "celery").strip().lower()
    checks.append(_check("worker_backend", True, backend))
    if backend == "celery":
        try:
            from infra.worker_health import celery_worker_online, celery_workers_required

            required = celery_workers_required()
            if required:
                online = celery_worker_online(timeout=2.0, cache_sec=0.0)
                checks.append(
                    _check(
                        "celery_worker",
                        online,
                        "online" if online else "run: python scripts/celery_worker.py",
                    )
                )
            else:
                checks.append(_check("celery_worker", True, "no worker flags enabled", warn=True))
        except Exception as exc:
            checks.append(_check("celery_worker", False, str(exc)[:200]))

    # LLM
    llm_key = (os.environ.get("LLM_API_KEY") or "").strip()
    checks.append(
        _check(
            "llm_api_key",
            bool(llm_key),
            "configured" if llm_key else "LLM_API_KEY empty — orchestrator/content disabled",
            warn=not bool(llm_key),
        )
    )

    # Publish queue
    pq = os.environ.get("PUBLISH_QUEUE_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
    checks.append(
        _check(
            "publish_queue",
            pq or backend == "thread",
            "enabled" if pq else "PUBLISH_QUEUE_ENABLED=0 — queue not consumed",
            warn=not pq and backend == "celery",
        )
    )

    # Auth (informational)
    auth = os.environ.get("API_AUTH_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
    checks.append(_check("api_auth", True, "enabled" if auth else "disabled (dev ok)", warn=False))

    failed = [c for c in checks if c["level"] == "fail"]
    warned = [c for c in checks if c["level"] == "warn"]
    return {
        "ok": not failed,
        "checks": checks,
        "failed": len(failed),
        "warnings": len(warned),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lingxi Engine local setup verification")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_checks()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("Lingxi Engine local setup")
        print("-" * 40)
        for c in report["checks"]:
            mark = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}[c["level"]]
            line = f"[{mark}] {c['name']}"
            if c.get("detail"):
                line += f" — {c['detail']}"
            print(line)
        print("-" * 40)
        if report["ok"]:
            print("All required checks passed.")
            if report["warnings"]:
                print(f"Warnings: {report['warnings']} (optional items)")
        else:
            print(f"Failed: {report['failed']} — fix above items and retry.")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
