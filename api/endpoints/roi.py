"""联合 ROI API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

import bootstrap

bootstrap.ensure_paths()

router = APIRouter(tags=["roi"])


@router.get("/api/roi/combined/{run_id}")
def get_combined_roi(run_id: str, persist: bool = Query(False, description="true=写入 metrics 与知识库")):
    from services.combined_roi import apply_combined_roi_for_run, resolve_run_roi_inputs, compute_combined_roi

    if persist:
        result = apply_combined_roi_for_run(run_id)
    else:
        pub, ad = resolve_run_roi_inputs(run_id)
        result = compute_combined_roi(publish_roi=pub, ad_roi=ad)
        if result.get("ok"):
            result["run_id"] = run_id
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result)
    return result


@router.get("/api/roi/metrics/{run_id}")
def get_run_metrics(run_id: str, limit: int = 50):
    from core.storage import metrics_for_run

    return {"ok": True, "run_id": run_id, "metrics": metrics_for_run(run_id, limit=limit)}


@router.get("/api/roi/export/csv")
def export_roi_csv_api(days: int = Query(30, ge=1, le=90)):
    from services.roi_export import export_roi_csv, roi_export_enabled

    if not roi_export_enabled():
        raise HTTPException(status_code=403, detail={"error": "roi_export_disabled"})
    csv_text = export_roi_csv(days=days)
    filename = f"matrix_roi_report_{days}d.csv"
    return Response(
        content=csv_text.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/roi/matrix/strategy/{run_id}")
def get_matrix_strategy(run_id: str):
    from services.matrix_strategy import plan_matrix_from_combined_roi

    result = plan_matrix_from_combined_roi(run_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result)
    return result


@router.get("/api/roi/report/status")
def roi_report_status():
    from services.report_scheduler import get_report_scheduler_status

    return get_report_scheduler_status()


@router.post("/api/roi/report/send")
def roi_report_send(days: int = Query(30, ge=1, le=90)):
    from services.roi_email import send_roi_report_email

    return send_roi_report_email(days=days)


@router.post("/api/roi/report/start")
def roi_report_start():
    from services.report_scheduler import start_report_scheduler

    started = start_report_scheduler()
    return {"ok": started, "message": "report scheduler started" if started else "ROI_REPORT_SCHEDULE_ENABLED=0"}


@router.post("/api/roi/alert/test")
def roi_alert_test(run_id: str = Query("test-run"), force: bool = Query(False)):
    from services.roi_alert import dispatch_roi_alerts

    return dispatch_roi_alerts(
        run_id=run_id,
        combined_roi=0.8,
        publish_roi=0.75,
        ad_roi=0.6,
        event="test",
        force=force,
    )


@router.get("/api/roi/alert/status")
def roi_alert_status():
    from services.alert_cleanup_scheduler import get_alert_cleanup_status
    from services.roi_alert import roi_alert_enabled, webhook_url
    from services.roi_alert_dedup import dedup_enabled, dedup_ttl_sec
    from services.roi_alert_format import webhook_provider

    status = get_alert_cleanup_status()
    status["alert_enabled"] = roi_alert_enabled()
    status["webhook_configured"] = bool(webhook_url())
    status["webhook_provider"] = webhook_provider()
    status["dedup_enabled"] = dedup_enabled()
    status["dedup_ttl_sec"] = dedup_ttl_sec()
    return status


@router.post("/api/roi/alert/cleanup")
def roi_alert_cleanup(retention_sec: int | None = Query(None, ge=3600, le=7776000)):
    from services.alert_cleanup_scheduler import run_alert_cleanup

    return run_alert_cleanup(retention_sec=retention_sec)


@router.post("/api/roi/alert/cleanup/start")
def roi_alert_cleanup_start():
    from services.alert_cleanup_scheduler import start_alert_cleanup_scheduler

    started = start_alert_cleanup_scheduler()
    return {"ok": started, "message": "alert cleanup scheduler started" if started else "ROI_ALERT_CLEANUP_ENABLED=0"}
