"""K8s readiness 探测 — 核心依赖（SQLite + 可选 Redis / Celery）。"""
from __future__ import annotations

import os
from typing import Any


def _check_sqlite() -> dict[str, Any]:
    try:
        from core.db import connect

        conn = connect()
        conn.execute("SELECT 1")
        conn.close()
        return {"ok": True, "service": "sqlite"}
    except Exception as exc:
        return {"ok": False, "service": "sqlite", "error": str(exc)[:200]}


def _check_redis() -> dict[str, Any]:
    try:
        import redis

        client = redis.Redis(
            host=os.environ.get("REDIS_HOST", "localhost"),
            port=int(os.environ.get("REDIS_PORT", "6379")),
            decode_responses=True,
            socket_connect_timeout=float(os.environ.get("REDIS_CONNECT_TIMEOUT", "0.5")),
            socket_timeout=float(os.environ.get("REDIS_SOCKET_TIMEOUT", "0.5")),
        )
        ok = bool(client.ping())
        return {"ok": ok, "service": "redis", "host": os.environ.get("REDIS_HOST", "localhost")}
    except Exception as exc:
        return {"ok": False, "service": "redis", "error": str(exc)[:200]}


def _worker_backend() -> str:
    return (os.environ.get("WORKER_BACKEND") or "celery").strip().lower()


def _leader_lock_required() -> bool:
    if _worker_backend() == "celery":
        return False
    return os.environ.get("WORKER_LEADER_LOCK_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")


def _redis_required() -> bool:
    if _worker_backend() == "celery":
        return True
    return _leader_lock_required()


async def check_readiness() -> dict[str, Any]:
    checks: list[dict[str, Any]] = [_check_sqlite()]
    if _redis_required():
        checks.append(_check_redis())
    celery_required = False
    try:
        from infra.worker_health import celery_workers_required, celery_worker_online

        celery_required = celery_workers_required()
        if celery_required:
            checks.append(
                {
                    "ok": celery_worker_online(),
                    "service": "celery_worker",
                }
            )
    except Exception as exc:
        if celery_required:
            checks.append({"ok": False, "service": "celery_worker", "error": str(exc)[:200]})
    ok = all(c.get("ok") for c in checks)
    return {
        "ok": ok,
        "ready": ok,
        "checks": checks,
        "worker_backend": _worker_backend(),
        "leader_lock_required": _leader_lock_required(),
        "redis_required": _redis_required(),
        "celery_worker_required": celery_required,
    }
