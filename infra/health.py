"""Phase 0 基础设施连通性探测。"""
from __future__ import annotations

import os
from typing import Any

import httpx


async def check_postgres() -> dict[str, Any]:
    try:
        from sqlalchemy import text

        from infra.database import engine

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"ok": True, "service": "postgres", "url": _mask_url(os.environ.get("DATABASE_URL", ""))}
    except Exception as exc:
        return {"ok": False, "service": "postgres", "error": str(exc)}


async def check_redis() -> dict[str, Any]:
    try:
        from infra.redis_client import redis_client

        pong = await redis_client.ping()
        return {"ok": bool(pong), "service": "redis", "host": os.environ.get("REDIS_HOST", "localhost")}
    except Exception as exc:
        return {"ok": False, "service": "redis", "error": str(exc)}


async def check_qdrant() -> dict[str, Any]:
    host = os.environ.get("QDRANT_HOST", "localhost")
    port = int(os.environ.get("QDRANT_PORT", "6333"))
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"http://{host}:{port}/healthz")
            if resp.status_code == 200:
                return {"ok": True, "service": "qdrant", "host": host, "port": port}
        return {"ok": False, "service": "qdrant", "error": f"HTTP {resp.status_code}"}
    except Exception as exc:
        return {"ok": False, "service": "qdrant", "error": str(exc)}


async def check_minio() -> dict[str, Any]:
    endpoint = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
    try:
        from infra.object_storage import ObjectStorage

        storage = ObjectStorage()
        ok = storage.ping()
        return {"ok": ok, "service": "minio", "endpoint": endpoint, "mode": storage.mode}
    except Exception as exc:
        return {"ok": False, "service": "minio", "error": str(exc)}


async def check_prometheus() -> dict[str, Any]:
    url = os.environ.get("PROMETHEUS_URL", "http://localhost:9090/-/healthy")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            ok = resp.status_code == 200
            return {"ok": ok, "service": "prometheus", "url": url}
    except Exception as exc:
        return {"ok": False, "service": "prometheus", "error": str(exc)}


def check_celery_broker() -> dict[str, Any]:
    broker = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/1")
    try:
        import redis

        r = redis.from_url(broker)
        pong = r.ping()
        return {"ok": bool(pong), "service": "celery_broker", "broker": broker}
    except Exception as exc:
        return {"ok": False, "service": "celery_broker", "error": str(exc)}


def check_celery_worker(timeout: float = 3.0) -> dict[str, Any]:
    try:
        from infra.task_queue import celery_app

        inspect = celery_app.control.inspect(timeout=timeout)
        stats = inspect.stats() if inspect else None
        if stats:
            workers = list(stats.keys())
            return {"ok": True, "service": "celery_worker", "workers": workers}
        return {"ok": False, "service": "celery_worker", "error": "no workers online"}
    except Exception as exc:
        return {"ok": False, "service": "celery_worker", "error": str(exc)}


def run_celery_task_sync() -> dict[str, Any]:
    """向 Celery 投递 health_check 任务并等待结果（需 worker 在线）。"""
    try:
        from infra.task_queue import health_check

        result = health_check.apply_async()
        payload = result.get(timeout=10)
        return {"ok": True, "service": "celery_task", "result": payload}
    except Exception as exc:
        return {"ok": False, "service": "celery_task", "error": str(exc)}


async def check_all(*, include_worker: bool = False) -> dict[str, Any]:
    checks = [
        await check_postgres(),
        await check_redis(),
        await check_qdrant(),
        await check_minio(),
        await check_prometheus(),
        check_celery_broker(),
    ]
    if include_worker:
        checks.append(check_celery_worker())
    ok = all(c.get("ok") for c in checks)
    try:
        from infra.metrics import set_infra_health

        for item in checks:
            svc = str(item.get("service") or "")
            if svc:
                set_infra_health(svc, bool(item.get("ok")))
    except Exception:
        pass
    return {"ok": ok, "checks": checks}


def _mask_url(url: str) -> str:
    if "@" not in url:
        return url
    prefix, rest = url.split("@", 1)
    if "://" in prefix:
        scheme, _ = prefix.split("://", 1)
        return f"{scheme}://***@{rest}"
    return url
