"""Storage domain: ad."""
from __future__ import annotations

import json
import os
from typing import Any

import bootstrap

from core.storage._common import _connect, _now, init_storage

def save_ad_campaign(
    *,
    run_id: str,
    campaign_id: str,
    platform: str = "douyin",
    keyword: str = "",
    daily_budget: float = 0,
    dry_run: bool = False,
) -> None:
    init_storage()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO ad_campaigns (run_id, campaign_id, platform, keyword, daily_budget, dry_run, updated_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, campaign_id, platform, keyword, daily_budget, 1 if dry_run else 0, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_ad_campaign_by_run(run_id: str) -> dict[str, Any] | None:
    init_storage()
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT run_id, campaign_id, platform, keyword, daily_budget, dry_run, last_report_json, updated_ts
            FROM ad_campaigns WHERE run_id=? ORDER BY id DESC LIMIT 1
            """,
            (run_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["last_report"] = json.loads(d.pop("last_report_json") or "{}")
        except Exception:
            d["last_report"] = {}
        d["dry_run"] = bool(d.get("dry_run"))
        return d
    finally:
        conn.close()


def update_ad_campaign_report(run_id: str, report: dict[str, Any]) -> None:
    init_storage()
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE ad_campaigns SET last_report_json=?, updated_ts=? WHERE run_id=?
            """,
            (json.dumps(report, ensure_ascii=False), _now(), run_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_ad_campaigns(*, limit: int = 20) -> list[dict[str, Any]]:
    init_storage()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT run_id, campaign_id, platform, keyword, daily_budget, dry_run, updated_ts
            FROM ad_campaigns ORDER BY id DESC LIMIT ?
            """,
            (max(1, limit),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


