"""多账号发布调度与队列。"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import bootstrap
from core.storage import enqueue_publish, list_publish_accounts, list_publish_queue, pick_publish_account
from services.publish.router import publish_to_platform


def accounts_config_path() -> Path:
    raw = (os.environ.get("PUBLISH_ACCOUNTS_PATH") or "data/publish_accounts.json").strip()
    p = Path(raw)
    if not p.is_absolute():
        p = bootstrap.project_root() / p
    return p


def load_accounts_file() -> list[dict[str, Any]]:
    path = accounts_config_path()
    if not path.is_file():
        default = [
            {"account_id": "default", "platform": "douyin", "label": "默认抖音", "storage_state": "data/state/douyin_creator_storage.json", "enabled": True},
            {"account_id": "xhs_1", "platform": "xiaohongshu", "label": "小红书1号", "storage_state": "data/state/xhs_creator_storage.json", "enabled": True},
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def list_accounts(*, platform: str = "", org_id: str = "", enabled_only: bool = True) -> list[dict[str, Any]]:
    from services.org_resources import filter_accounts_by_org

    rows = load_accounts_file()
    if enabled_only:
        rows = [r for r in rows if r.get("enabled", True)]
    if platform:
        plat = platform.strip().lower()
        if plat == "xhs":
            plat = "xiaohongshu"
        rows = [r for r in rows if str(r.get("platform") or "").strip().lower() == plat]
    return filter_accounts_by_org(rows, org_id)


def pick_publish_account_for_org(platform: str, org_id: str = "") -> str | None:
    """按 org 过滤后选择今日配额最充足的账号。"""
    import datetime

    from core.storage import get_publish_state

    accounts = list_accounts(platform=platform, org_id=org_id, enabled_only=True)
    if not accounts:
        accounts = list_publish_accounts(platform=platform, enabled_only=True)
    if not accounts:
        return None
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    best_id = None
    best_score = -1
    for acc in accounts:
        aid = str(acc.get("account_id") or "default")
        st = get_publish_state(platform, aid)
        count = int(st.get("day_count") or 0) if st.get("last_day") == today else 0
        limit = int(acc.get("daily_limit") or os.environ.get("PUBLISH_DAILY_LIMIT", "4") or 4)
        remain = limit - count
        if remain > best_score:
            best_score = remain
            best_id = aid
    return best_id if best_score > 0 else None


def sync_accounts_to_db() -> int:
    from core.storage import upsert_publish_account

    n = 0
    for row in load_accounts_file():
        if not row.get("enabled", True):
            continue
        upsert_publish_account(
            platform=str(row.get("platform") or "douyin"),
            account_id=str(row.get("account_id") or "default"),
            label=str(row.get("label") or ""),
            storage_state=str(row.get("storage_state") or ""),
            daily_limit=int(row.get("daily_limit") or os.environ.get("PUBLISH_DAILY_LIMIT", "4") or 4),
        )
        n += 1
    return n


def schedule_publish(
    *,
    platform: str,
    video_path: str,
    script: str,
    title: str = "",
    account_id: str = "",
    run_id: str = "",
    scheduled_ts: int = 0,
    priority: int = 0,
    org_id: str = "",
) -> dict[str, Any]:
    sync_accounts_to_db()
    plat = platform.strip().lower()
    if plat == "xhs":
        plat = "xiaohongshu"
    aid = account_id or pick_publish_account_for_org(plat, org_id) or pick_publish_account(plat) or "default"
    job_id = str(uuid.uuid4())
    from services.publish_priority import resolve_publish_priority

    pri = resolve_publish_priority(run_id, priority)
    scheduled = scheduled_ts
    rate_meta = None
    try:
        from services.publish_rate_limit import resolve_scheduled_ts

        slot = resolve_scheduled_ts(
            platform=plat,
            account_id=aid,
            run_id=run_id,
            requested_ts=int(scheduled_ts or 0),
        )
        if not slot.get("ok"):
            return {"ok": False, **slot}
        scheduled = int(slot.get("scheduled_ts") or scheduled_ts or 0)
        rate_meta = slot
    except Exception:
        pass
    enqueue_publish(
        job_id=job_id,
        platform=plat,
        account_id=aid,
        video_path=video_path,
        script=script,
        title=title,
        run_id=run_id,
        scheduled_ts=scheduled,
        priority=pri,
        org_id=org_id,
    )
    try:
        from services.dashboard_hub import notify_dashboard_update

        notify_dashboard_update(reason="publish_queue_enqueue")
    except Exception:
        pass
    return {
        "ok": True,
        "job_id": job_id,
        "platform": plat,
        "account_id": aid,
        "scheduled_ts": scheduled,
        "priority": pri,
        "rate_limit": rate_meta,
    }


def run_publish_queue(*, limit: int = 10, dry_run: bool = False) -> dict[str, Any]:
    """执行到期发布任务。"""
    sync_accounts_to_db()
    jobs = list_publish_queue(status="queued", limit=limit)
    results = []
    for job in jobs:
        plat = str(job.get("platform") or "douyin")
        aid = str(job.get("account_id") or "default")
        storage = str(job.get("storage_state") or "")
        if storage:
            env_key = f"{plat.upper()}_PUBLISH_STORAGE_STATE"
            if plat == "xiaohongshu":
                env_key = "XHS_PUBLISH_STORAGE_STATE"
            os.environ[env_key] = str(Path(storage).resolve()) if not Path(storage).is_absolute() else storage

        from core.storage import update_publish_queue_status

        if dry_run:
            update_publish_queue_status(job["job_id"], "dry_run", {"dry_run": True})
            results.append({"job_id": job["job_id"], "ok": True, "dry_run": True})
            continue

        out = publish_to_platform(
            plat,
            video_path=str(job.get("video_path") or ""),
            script=str(job.get("script") or ""),
            title=str(job.get("title") or ""),
            account_id=aid,
            run_id=str(job.get("run_id") or ""),
        )
        if out.get("success"):
            try:
                from services.publish_feedback import apply_publish_success_feedback

                out["roi_feedback"] = apply_publish_success_feedback(
                    platform=plat,
                    script=str(job.get("script") or ""),
                    title=str(job.get("title") or ""),
                    post_url=str(out.get("post_url") or ""),
                    run_id=str(job.get("run_id") or ""),
                    account_id=aid,
                    job_id=str(job.get("job_id") or ""),
                )
            except Exception as exc:
                out["roi_feedback_error"] = str(exc)[:200]
            update_publish_queue_status(job["job_id"], "published", out)
        else:
            from services.publish_retry import handle_publish_failure

            out["retry"] = handle_publish_failure(job, out)
        results.append({"job_id": job["job_id"], **out})

    ok_n = sum(1 for r in results if r.get("success") or r.get("dry_run"))
    return {"ok": True, "processed": len(results), "success": ok_n, "results": results}


def matrix_publish_plan(
    *,
    video_path: str,
    script: str,
    title: str = "",
    platforms: list[str] | None = None,
    run_id: str = "",
    priority: int = 0,
    org_id: str = "",
) -> dict[str, Any]:
    """多平台多账号批量入队。"""
    sync_accounts_to_db()
    plats = platforms or ["douyin", "xiaohongshu"]
    jobs = []
    for plat in plats:
        accounts = list_accounts(platform=plat, org_id=org_id, enabled_only=True)
        if not accounts:
            accounts = list_publish_accounts(platform=plat, enabled_only=True)
        if not accounts:
            jobs.append(schedule_publish(platform=plat, video_path=video_path, script=script, title=title, run_id=run_id, priority=priority, org_id=org_id))
        else:
            for acc in accounts[: int(os.environ.get("PUBLISH_ACCOUNTS_PER_PLATFORM", "2") or 2)]:
                jobs.append(
                    schedule_publish(
                        platform=plat,
                        video_path=video_path,
                        script=script,
                        title=title,
                        account_id=str(acc.get("account_id") or "default"),
                        run_id=run_id,
                        priority=priority,
                        org_id=org_id,
                    )
                )
    return {"ok": True, "queued": len(jobs), "jobs": jobs}
