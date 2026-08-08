"""自动发布 API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import bootstrap

bootstrap.ensure_paths()

router = APIRouter(tags=["publish"])


class PublishPayload(BaseModel):
    platform: str = Field(default="douyin", description="douyin | xiaohongshu | shipinhao")
    video_path: str = Field(..., min_length=1, description="本地视频绝对/相对路径")
    script: str = Field(default="", description="口播文案，用于标题/描述/标签")
    title: str = Field(default="", max_length=40)
    dry_run: bool = Field(default=False, description="仅生成发布元数据，不实际上传")
    account_id: str = Field(default="default")
    run_id: str = Field(default="")
    keyword: str = Field(default="")


class PublishMultiPayload(BaseModel):
    platforms: list[str] = Field(default_factory=lambda: ["douyin"])
    video_path: str = Field(...)
    script: str = Field(default="")
    title: str = Field(default="")
    dry_run: bool = Field(default=False)


@router.get("/api/publish/status")
def publish_status(platform: str = "douyin"):
    from services.publish.router import health, supported_platforms

    return {
        "ok": True,
        "supported": supported_platforms(),
        "health": health(platform),
    }


@router.get("/api/publish/readiness")
def publish_readiness():
    from services.publish_readiness import all_publish_readiness

    return all_publish_readiness()


@router.get("/api/tunnel/status")
def tunnel_status_api(port: int = 9200):
    from services.tunnel import tunnel_status

    return tunnel_status(port=port)


@router.get("/api/docker/compose/status")
def docker_compose_status():
    from services.compose_profiles import compose_status

    return compose_status()


@router.get("/api/deploy/status")
def deploy_status_api():
    from services.deploy_status import deploy_manifest_status, validate_helm_chart, validate_k8s_yaml

    return {
        "ok": True,
        "manifest": deploy_manifest_status(),
        "k8s_yaml": validate_k8s_yaml(),
        "helm": validate_helm_chart(),
    }


@router.get("/api/deploy/helm/status")
def deploy_helm_status_api():
    from services.deploy_status import helm_chart_status, validate_helm_chart

    chart = helm_chart_status()
    validation = validate_helm_chart()
    return {
        "ok": bool(chart.get("ok")) and bool(validation.get("ok")),
        "chart": chart,
        "validation": validation,
    }


@router.get("/api/publish/logs")
def publish_logs(limit: int = 20):
    from core.storage import list_publish_log

    return {"ok": True, "logs": list_publish_log(limit=limit)}


@router.post("/api/publish/run")
def publish_run(body: PublishPayload):
    from services.publish.router import publish_to_platform

    result = publish_to_platform(
        body.platform,
        video_path=body.video_path,
        script=body.script,
        title=body.title,
        dry_run=body.dry_run,
        account_id=body.account_id,
        run_id=body.run_id,
        keyword=body.keyword,
    )
    if not result.get("success"):
        err = str(result.get("error") or "publish_failed")
        if err in ("storage_state_missing", "creator_login_required", "publish_disabled", "quota_exceeded"):
            raise HTTPException(status_code=503, detail=result)
        raise HTTPException(status_code=400, detail=result)
    return {"ok": True, **result}


@router.post("/api/publish/run_multi")
def publish_run_multi(body: PublishMultiPayload):
    from services.publish.router import publish_multi

    result = publish_multi(
        body.platforms,
        video_path=body.video_path,
        script=body.script,
        title=body.title,
        dry_run=body.dry_run,
    )
    return {"ok": bool(result.get("success")), **result}


class PublishSchedulePayload(BaseModel):
    platform: str = Field(default="douyin")
    video_path: str = Field(..., min_length=1)
    script: str = Field(default="")
    title: str = Field(default="")
    account_id: str = Field(default="")
    run_id: str = Field(default="")
    scheduled_ts: int = Field(default=0, ge=0)
    priority: int = Field(default=0, ge=0, le=100, description="越大越优先，0=自动")
    org_id: str = Field(default="")


class PublishQueuePriorityPayload(BaseModel):
    priority: int = Field(..., ge=0, le=100)
    org_id: str = Field(default="")


class PublishQueueBumpPayload(BaseModel):
    delta: int = Field(default=5, ge=-50, le=50)
    org_id: str = Field(default="")


class PublishMatrixPayload(BaseModel):
    video_path: str = Field(..., min_length=1)
    script: str = Field(default="")
    title: str = Field(default="")
    platforms: list[str] = Field(default_factory=lambda: ["douyin", "xiaohongshu"])
    run_id: str = Field(default="")
    priority: int = Field(default=0, ge=0, le=100)


@router.get("/api/publish/accounts")
def publish_accounts(platform: str = "", org_id: str = ""):
    from services.publish.scheduler import list_accounts, sync_accounts_to_db
    from core.storage import list_publish_accounts

    sync_accounts_to_db()
    file_accounts = list_accounts(platform=platform.strip(), org_id=org_id.strip())
    db_accounts = list_publish_accounts(platform=platform.strip())
    return {
        "ok": True,
        "org_id": org_id.strip(),
        "accounts": file_accounts or db_accounts,
        "source": "file" if file_accounts else "db",
    }


@router.post("/api/publish/schedule")
def publish_schedule(body: PublishSchedulePayload):
    from services.publish.scheduler import schedule_publish

    return schedule_publish(
        platform=body.platform,
        video_path=body.video_path,
        script=body.script,
        title=body.title,
        account_id=body.account_id,
        run_id=body.run_id,
        scheduled_ts=body.scheduled_ts,
        priority=body.priority,
        org_id=body.org_id.strip(),
    )


@router.post("/api/publish/queue/run")
def publish_queue_run(limit: int = 10, dry_run: bool = False):
    from services.publish.scheduler import run_publish_queue

    return run_publish_queue(limit=limit, dry_run=dry_run)


class PublishMatrixAutoPayload(BaseModel):
    run_id: str = Field(..., min_length=1)
    video_path: str = Field(..., min_length=1)
    script: str = Field(default="")
    title: str = Field(default="")
    platforms: list[str] = Field(default_factory=list, description="留空则按联合 ROI 策略自动选择")


@router.post("/api/publish/matrix/auto")
def publish_matrix_auto(body: PublishMatrixAutoPayload):
    from services.matrix_strategy import auto_matrix_publish

    plats = body.platforms if body.platforms else None
    result = auto_matrix_publish(
        run_id=body.run_id,
        video_path=body.video_path,
        script=body.script,
        title=body.title,
        platforms=plats,
    )
    if not result.get("ok") and result.get("action") != "skip":
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/api/publish/matrix")
def publish_matrix(body: PublishMatrixPayload):
    from services.publish.scheduler import matrix_publish_plan

    return matrix_publish_plan(
        video_path=body.video_path,
        script=body.script,
        title=body.title,
        platforms=body.platforms,
        run_id=body.run_id,
        priority=body.priority,
    )


@router.get("/api/publish/queue/status")
def publish_queue_status():
    from services.publish_worker import get_worker_status

    return get_worker_status()


@router.post("/api/publish/queue/start")
def publish_queue_start():
    from services.publish_worker import start_background_worker

    started = start_background_worker()
    return {"ok": started, "message": "background worker started" if started else "PUBLISH_QUEUE_ENABLED=0"}


@router.post("/api/publish/queue/trigger")
def publish_queue_trigger(sync: bool = False, dry_run: bool = False):
    from services.publish_worker import run_queue_once, trigger_worker_async

    if sync:
        return run_queue_once(dry_run=dry_run)
    return trigger_worker_async(dry_run=dry_run)


@router.post("/api/publish/queue/refresh-priority")
def publish_queue_refresh_priority(limit: int = 100, org_id: str = "", force: bool = False):
    from services.publish_priority import refresh_queue_priorities

    return refresh_queue_priorities(limit=limit, org_id=org_id.strip(), force=force)


@router.patch("/api/publish/queue/{job_id}/priority")
def publish_queue_set_priority(job_id: str, body: PublishQueuePriorityPayload):
    from services.publish_queue_ops import set_job_priority

    result = set_job_priority(job_id=job_id, priority=body.priority, org_id=body.org_id.strip())
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/api/publish/queue/{job_id}/bump")
def publish_queue_bump_priority(job_id: str, body: PublishQueueBumpPayload):
    from services.publish_queue_ops import bump_job_priority

    result = bump_job_priority(job_id=job_id, delta=body.delta, org_id=body.org_id.strip())
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/api/publish/queue/{job_id}/pin")
def publish_queue_pin(job_id: str, org_id: str = ""):
    from services.publish_queue_ops import pin_job_priority

    result = pin_job_priority(job_id=job_id, org_id=org_id.strip())
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/api/publish/queue/{job_id}/cancel")
def publish_queue_cancel(job_id: str, org_id: str = "", reason: str = ""):
    from services.publish_queue_ops import cancel_queued_job

    result = cancel_queued_job(job_id=job_id, org_id=org_id.strip(), reason=reason)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return result
