"""Storage domain: publish."""
from __future__ import annotations

import json
import os
from typing import Any

import bootstrap

from core.storage._common import _connect, _now, init_storage

def update_publish_queue_priority(
    job_id: str,
    priority: int,
    *,
    source: str = "auto",
    roi_meta: dict[str, Any] | None = None,
) -> None:
    init_storage()
    row = get_publish_queue_job(job_id)
    payload = dict((row or {}).get("payload") or {})
    payload["priority"] = int(priority)
    src = (source or "auto").strip().lower()
    if src == "manual":
        payload["priority_manual"] = True
    elif src == "pin":
        payload["priority_pinned"] = True
        payload["priority_manual"] = True
    elif src == "auto":
        payload["priority_auto_ts"] = _now()
        if roi_meta:
            for key in ("combined_roi_score", "grade", "priority_delta"):
                if key in roi_meta and roi_meta[key] is not None:
                    payload[key] = roi_meta[key]
    conn = _connect()
    try:
        conn.execute(
            "UPDATE publish_queue SET payload_json=?, updated_ts=? WHERE job_id=?",
            (json.dumps(payload, ensure_ascii=False), _now(), job_id),
        )
        conn.commit()
    finally:
        conn.close()


def save_execution_job(job_id: str, run_id: str, stage: str, payload: dict[str, Any]) -> None:
    init_storage()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO execution_jobs (job_id, run_id, stage, payload_json, updated_ts)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET stage=excluded.stage, payload_json=excluded.payload_json, updated_ts=excluded.updated_ts
            """,
            (job_id, run_id, stage, json.dumps(payload, ensure_ascii=False), _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_publish_state(platform: str, account_id: str = "default") -> dict[str, Any]:
    init_storage()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT last_publish_ts, last_day, day_count FROM publish_state WHERE platform=? AND account_id=?",
            (platform, account_id),
        ).fetchone()
        if not row:
            return {"last_publish_ts": 0, "last_day": "", "day_count": 0}
        return {"last_publish_ts": row[0], "last_day": row[1], "day_count": row[2]}
    finally:
        conn.close()


def set_publish_state(platform: str, account_id: str, data: dict[str, Any]) -> None:
    init_storage()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO publish_state (platform, account_id, last_publish_ts, last_day, day_count)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(platform, account_id) DO UPDATE SET
              last_publish_ts=excluded.last_publish_ts,
              last_day=excluded.last_day,
              day_count=excluded.day_count
            """,
            (
                platform,
                account_id,
                int(data.get("last_publish_ts") or 0),
                str(data.get("last_day") or ""),
                int(data.get("day_count") or 0),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def append_publish_log(
    *,
    platform: str,
    video_path: str,
    post_url: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    init_storage()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO publish_log (platform, video_path, post_url, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (platform, video_path, post_url, json.dumps(metadata or {}, ensure_ascii=False), _now()),
        )
        conn.commit()
    finally:
        conn.close()


def upsert_publish_account(
    *,
    platform: str,
    account_id: str,
    label: str = "",
    storage_state: str = "",
    daily_limit: int = 4,
    enabled: bool = True,
) -> None:
    init_storage()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO publish_accounts (platform, account_id, label, storage_state, daily_limit, enabled)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(platform, account_id) DO UPDATE SET
              label=excluded.label, storage_state=excluded.storage_state,
              daily_limit=excluded.daily_limit, enabled=excluded.enabled
            """,
            (platform, account_id, label, storage_state, daily_limit, 1 if enabled else 0),
        )
        conn.commit()
    finally:
        conn.close()


def list_publish_accounts(*, platform: str = "", enabled_only: bool = True) -> list[dict[str, Any]]:
    init_storage()
    conn = _connect()
    try:
        if platform:
            rows = conn.execute(
                "SELECT platform, account_id, label, storage_state, daily_limit, enabled FROM publish_accounts WHERE platform=?",
                (platform,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT platform, account_id, label, storage_state, daily_limit, enabled FROM publish_accounts"
            ).fetchall()
        out = [dict(r) for r in rows]
        if enabled_only:
            out = [r for r in out if r.get("enabled")]
        return out
    finally:
        conn.close()


def pick_publish_account(platform: str) -> str | None:
    """选择今日配额最充足的账号。"""
    import datetime

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
        limit = int(acc.get("daily_limit") or 4)
        remain = limit - count
        if remain > best_score:
            best_score = remain
            best_id = aid
    return best_id if best_score > 0 else None


def enqueue_publish(
    *,
    job_id: str,
    platform: str,
    account_id: str,
    video_path: str,
    script: str,
    title: str = "",
    run_id: str = "",
    scheduled_ts: int = 0,
    priority: int = 0,
    org_id: str = "",
) -> None:
    init_storage()
    accs = list_publish_accounts(platform=platform)
    storage = ""
    for a in accs:
        if str(a.get("account_id")) == account_id:
            storage = str(a.get("storage_state") or "")
            break
    pri = int(priority)
    if pri <= 0 and run_id:
        pri = int(os.environ.get("PUBLISH_QUEUE_RUN_PRIORITY", "5") or 5)
    payload: dict[str, Any] = {"storage_state": storage, "priority": pri}
    if org_id:
        payload["org_id"] = str(org_id).strip()
    ts = _now()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO publish_queue
            (job_id, platform, account_id, video_path, script, title, run_id, status, scheduled_ts, payload_json, created_ts, updated_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)
            """,
            (
                job_id,
                platform,
                account_id,
                video_path,
                script,
                title,
                run_id,
                int(scheduled_ts or ts),
                json.dumps(payload, ensure_ascii=False),
                ts,
                ts,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_publish_queue(*, status: str = "queued", limit: int = 20) -> list[dict[str, Any]]:
    init_storage()
    now = _now()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT job_id, platform, account_id, video_path, script, title, run_id, status, scheduled_ts, payload_json
            FROM publish_queue
            WHERE status=? AND scheduled_ts <= ?
            ORDER BY CAST(COALESCE(json_extract(payload_json, '$.priority'), '0') AS INTEGER) DESC, scheduled_ts ASC
            LIMIT ?
            """,
            (status, now, max(1, limit)),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                payload = json.loads(d.pop("payload_json") or "{}")
                d["storage_state"] = payload.get("storage_state") or ""
                d["retry_count"] = int(payload.get("retry_count") or 0)
                d["last_error"] = payload.get("last_error") or ""
                d["priority"] = int(payload.get("priority") or 0)
            except Exception:
                d["storage_state"] = ""
                d["retry_count"] = 0
                d["last_error"] = ""
                d["priority"] = 0
            out.append(d)
        return out
    finally:
        conn.close()


def get_publish_queue_job(job_id: str) -> dict[str, Any] | None:
    init_storage()
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT job_id, platform, account_id, video_path, script, title, run_id, status, scheduled_ts, payload_json
            FROM publish_queue WHERE job_id=?
            """,
            (job_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            payload = json.loads(d.pop("payload_json") or "{}")
            d["payload"] = payload
            d["priority"] = int(payload.get("priority") or 0)
            d["org_id"] = str(payload.get("org_id") or "")
        except Exception:
            d["payload"] = {}
            d["priority"] = 0
            d["org_id"] = ""
        return d
    finally:
        conn.close()


def requeue_publish_job(
    *,
    job_id: str,
    retry_count: int,
    scheduled_ts: int,
    last_error: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    init_storage()
    row = get_publish_queue_job(job_id)
    payload = dict((row or {}).get("payload") or {})
    payload["retry_count"] = retry_count
    payload["last_error"] = last_error
    base_pri = int(payload.get("priority") or 0)
    payload["priority"] = max(0, base_pri - 1)
    if extra:
        payload.update(extra)
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE publish_queue
            SET status='queued', scheduled_ts=?, payload_json=?, updated_ts=?
            WHERE job_id=?
            """,
            (int(scheduled_ts), json.dumps(payload, ensure_ascii=False), _now(), job_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_publish_queue_items(*, status: str = "", limit: int = 50, org_id: str = "") -> list[dict[str, Any]]:
    """列出队列任务（dashboard 用，不过滤 scheduled_ts）。"""
    from services.tenant import filter_by_org, item_org_id

    init_storage()
    conn = _connect()
    try:
        if status:
            rows = conn.execute(
                """
                SELECT job_id, platform, account_id, video_path, script, title, run_id, status, scheduled_ts, payload_json, updated_ts
                FROM publish_queue WHERE status=?
                ORDER BY CAST(COALESCE(json_extract(payload_json, '$.priority'), '0') AS INTEGER) DESC, updated_ts DESC
                LIMIT ?
                """,
                (status, max(1, limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT job_id, platform, account_id, video_path, script, title, run_id, status, scheduled_ts, payload_json, updated_ts
                FROM publish_queue
                ORDER BY CAST(COALESCE(json_extract(payload_json, '$.priority'), '0') AS INTEGER) DESC, updated_ts DESC
                LIMIT ?
                """,
                (max(1, limit),),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                payload = json.loads(d.pop("payload_json") or "{}")
                d["payload"] = payload
                d["retry_count"] = int(payload.get("retry_count") or 0)
                d["last_error"] = payload.get("last_error") or ""
                d["priority"] = int(payload.get("priority") or 0)
                d["org_id"] = str(payload.get("org_id") or "")
            except Exception:
                d["payload"] = {}
                d["retry_count"] = 0
                d["last_error"] = ""
                d["priority"] = 0
                d["org_id"] = ""
            out.append(d)
        return filter_by_org(out, org_id)
    finally:
        conn.close()


def update_publish_queue_schedule(
    job_id: str,
    scheduled_ts: int,
    payload_extra: dict[str, Any] | None = None,
) -> None:
    init_storage()
    existing = get_publish_queue_job(job_id)
    merged = dict((existing or {}).get("payload") or {})
    if payload_extra:
        merged.update(payload_extra)
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE publish_queue SET scheduled_ts=?, payload_json=?, updated_ts=? WHERE job_id=?
            """,
            (int(scheduled_ts), json.dumps(merged, ensure_ascii=False), _now(), job_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_publish_queue_status(job_id: str, status: str, payload: dict[str, Any] | None = None) -> None:
    init_storage()
    merged = dict(payload or {})
    if payload is not None:
        existing = get_publish_queue_job(job_id)
        if existing and existing.get("payload"):
            base = dict(existing["payload"])
            base.update(payload)
            merged = base
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE publish_queue SET status=?, payload_json=?, updated_ts=? WHERE job_id=?
            """,
            (status, json.dumps(merged, ensure_ascii=False), _now(), job_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_publish_log(*, limit: int = 20) -> list[dict[str, Any]]:
    init_storage()
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, platform, video_path, post_url, created_at FROM publish_log ORDER BY id DESC LIMIT ?",
            (max(1, limit),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
