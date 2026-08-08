"""五层 AI 智能体矩阵 — 独立 API 服务。"""
from __future__ import annotations

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.auth import ApiAuthMiddleware
from api.endpoints.ad import router as ad_router
from api.endpoints.agents import router as agents_router
from api.endpoints.asr import router as asr_router
from api.endpoints.auth import router as auth_router
from api.endpoints.campaign import router as campaign_router
from api.endpoints.dashboard import router as dashboard_router
from api.endpoints.douyin import router as douyin_router
from api.endpoints.engineering import router as engineering_router
from api.endpoints.infra import router as infra_router
from api.endpoints.memory import router as memory_router
from api.endpoints.monitor import router as monitor_router
from api.endpoints.org import router as org_router
from api.endpoints.orchestrator import router as orchestrator_router
from api.endpoints.perception import router as perception_router
from api.endpoints.publish import router as publish_router
from api.endpoints.review import router as review_router
from api.endpoints.roi import router as roi_router
from api.endpoints.rpa import router as rpa_router
from api.endpoints.runtime import router as runtime_router
from api.endpoints.video import router as video_router
from api.endpoints.workflow import router as workflow_router
from api.endpoints.xhs import router as xhs_router
from config.settings import get_settings

log = logging.getLogger(__name__)


def _start_background_workers() -> None:
    settings = get_settings()
    from services.workers.runtime import use_celery_workers

    if use_celery_workers():
        from infra.task_queue import refresh_beat_schedule

        scheduled = refresh_beat_schedule()
        log.info(
            "Worker backend=celery; API 不启动 in-process 线程，已注册 beat 任务: %s",
            list(scheduled.keys()) or "(none enabled)",
        )
    if settings.ad_poll_enabled:
        from services.ad_scheduler import start_background_poller

        start_background_poller()
    if settings.publish_queue_enabled:
        from services.publish_worker import start_background_worker

        start_background_worker()
    if settings.roi_report_schedule_enabled:
        from services.report_scheduler import start_report_scheduler

        start_report_scheduler()
    if settings.roi_alert_cleanup_enabled:
        from services.alert_cleanup_scheduler import start_alert_cleanup_scheduler

        start_alert_cleanup_scheduler()
    if settings.perception_schedule_enabled:
        from services.perception_scheduler import start_perception_scheduler

        start_perception_scheduler()
    if settings.post_publish_monitor_enabled:
        from services.post_publish_monitor_worker import start_monitor_worker

        start_monitor_worker()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    errors = settings.validate_production()
    if errors:
        raise RuntimeError("Production secret check failed:\n- " + "\n".join(errors))
    from core.db import init_storage

    init_storage()
    _start_background_workers()
    yield


settings = get_settings()

app = FastAPI(
    title="灵犀引擎",
    version="1.0.0",
    description="AI 感知·决策·执行，人类点头确认与应急兜底",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ApiAuthMiddleware)

_static_dir = bootstrap.project_root() / "api" / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

app.include_router(auth_router)
app.include_router(orchestrator_router)
app.include_router(douyin_router)
app.include_router(xhs_router)
app.include_router(publish_router)
app.include_router(ad_router)
app.include_router(dashboard_router)
app.include_router(asr_router)
app.include_router(roi_router)
app.include_router(perception_router)
app.include_router(review_router)
app.include_router(monitor_router)
app.include_router(video_router)
app.include_router(runtime_router)
app.include_router(org_router)
app.include_router(infra_router)
app.include_router(memory_router)
app.include_router(agents_router)
app.include_router(campaign_router)
app.include_router(workflow_router)
app.include_router(engineering_router)
app.include_router(rpa_router)


@app.get("/")
def root(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept and "application/json" not in accept.split(",")[0]:
        return RedirectResponse("/dashboard")
    return {
        "ok": True,
        "service": "灵犀引擎",
        "dashboard_home": "/dashboard",
        "docs": "/docs",
    }


@app.get("/api/health")
def health():
    import time

    s = get_settings()
    return {
        "ok": True,
        "service": "灵犀引擎",
        "ts": int(time.time()),
        "environment": s.environment,
        "publish_queue_worker": "1" if s.publish_queue_enabled else "0",
        "perception_scheduler": "1" if s.perception_schedule_enabled else "0",
        "api_auth_enabled": "1" if s.api_auth_enabled else "0",
        "worker_leader_lock": "1" if s.worker_leader_lock_enabled else "0",
        "worker_backend": s.worker_backend,
        "db_schema_version": __import__("core.db", fromlist=["schema_version"]).schema_version(),
        "db_alembic_revision": __import__("core.db", fromlist=["alembic_revision"]).alembic_revision(),
    }


@app.get("/api/health/ready")
async def health_ready():
    from fastapi import Response

    from infra.readiness import check_readiness

    result = await check_readiness()
    if not result.get("ok"):
        return JSONResponse(status_code=503, content=result)
    return result


@app.get("/metrics")
def metrics():
    from fastapi import Response

    from infra.metrics import render_metrics

    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)


if __name__ == "__main__":
    import uvicorn

    port = get_settings().api_port
    uvicorn.run("api_server:app", host="0.0.0.0", port=port, reload=False)
