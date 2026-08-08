"""Phase 0 基础设施 — API 路由。"""
from __future__ import annotations

from fastapi import APIRouter, Response

router = APIRouter(prefix="/api/infra", tags=["infra"])


@router.get("/health")
async def infra_health(worker: bool = False):
    from infra.health import check_all

    return await check_all(include_worker=worker)


@router.get("/health/postgres")
async def postgres_health():
    from infra.health import check_postgres

    return await check_postgres()


@router.get("/health/redis")
async def redis_health():
    from infra.health import check_redis

    return await check_redis()


@router.get("/health/qdrant")
async def qdrant_health():
    from infra.health import check_qdrant

    return await check_qdrant()


@router.get("/health/minio")
async def minio_health():
    from infra.health import check_minio

    return await check_minio()


@router.get("/health/celery")
async def celery_health():
    from infra.health import check_celery_broker, check_celery_worker, run_celery_task_sync

    broker = check_celery_broker()
    worker = check_celery_worker()
    task = run_celery_task_sync() if worker.get("ok") else {"ok": False, "skipped": True}
    return {"broker": broker, "worker": worker, "task": task}


@router.get("/metrics")
async def prometheus_metrics():
    from infra.metrics import render_metrics

    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)
