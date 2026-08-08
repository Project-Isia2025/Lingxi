"""Storage domain: metrics."""
from __future__ import annotations

import json
import os
from typing import Any

import bootstrap

from core.storage._common import _connect, _now, init_storage

def metrics_record(*, run_id: str, event_type: str, value: float = 1.0, payload: dict | None = None) -> None:
    init_storage()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO content_metrics (run_id, event_type, metric_value, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, event_type, value, json.dumps(payload or {}, ensure_ascii=False), _now()),
        )
        conn.commit()
    finally:
        conn.close()


def metrics_summary(*, days: int = 14) -> dict[str, Any]:
    init_storage()
    since = _now() - max(1, min(days, 90)) * 86400
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT event_type, COUNT(*) c, SUM(metric_value) s
            FROM content_metrics WHERE created_at >= ?
            GROUP BY event_type
            """,
            (since,),
        ).fetchall()
        by_event = {str(r["event_type"]): {"count": int(r["c"]), "sum": float(r["s"] or 0)} for r in rows}
        leads = int((by_event.get("lead") or {}).get("count") or 0)
        return {"days": days, "by_event": by_event, "leads_total": leads, "hotspots_active": 0}
    finally:
        conn.close()


def metrics_latest(run_id: str, event_type: str) -> float | None:
    init_storage()
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT metric_value FROM content_metrics
            WHERE run_id=? AND event_type=?
            ORDER BY created_at DESC LIMIT 1
            """,
            (run_id, event_type),
        ).fetchone()
        if not row:
            return None
        return float(row[0])
    finally:
        conn.close()


def metrics_for_run(run_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    init_storage()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT event_type, metric_value, payload_json, created_at
            FROM content_metrics WHERE run_id=?
            ORDER BY created_at DESC LIMIT ?
            """,
            (run_id, max(1, limit)),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d.pop("payload_json") or "{}")
            except Exception:
                d["payload"] = {}
            out.append(d)
        return out
    finally:
        conn.close()


def metrics_daily_series(*, days: int = 14, event_types: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    """按日聚合指标（图表用）。"""
    init_storage()
    since = _now() - max(1, min(days, 90)) * 86400
    conn = _connect()
    try:
        if event_types:
            placeholders = ",".join("?" * len(event_types))
            rows = conn.execute(
                f"""
                SELECT strftime('%Y-%m-%d', created_at, 'unixepoch') AS day,
                       event_type,
                       COUNT(*) AS cnt,
                       AVG(metric_value) AS avg_value,
                       SUM(metric_value) AS sum_value
                FROM content_metrics
                WHERE created_at >= ? AND event_type IN ({placeholders})
                GROUP BY day, event_type
                ORDER BY day ASC
                """,
                (since, *event_types),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT strftime('%Y-%m-%d', created_at, 'unixepoch') AS day,
                       event_type,
                       COUNT(*) AS cnt,
                       AVG(metric_value) AS avg_value,
                       SUM(metric_value) AS sum_value
                FROM content_metrics
                WHERE created_at >= ?
                GROUP BY day, event_type
                ORDER BY day ASC
                """,
                (since,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def metrics_export_rows(
    *,
    days: int = 30,
    event_types: tuple[str, ...] | None = None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    init_storage()
    since = _now() - max(1, min(days, 90)) * 86400
    conn = _connect()
    try:
        if event_types:
            placeholders = ",".join("?" * len(event_types))
            rows = conn.execute(
                f"""
                SELECT run_id, event_type, metric_value, payload_json, created_at
                FROM content_metrics
                WHERE created_at >= ? AND event_type IN ({placeholders})
                ORDER BY created_at DESC LIMIT ?
                """,
                (since, *event_types, max(1, limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT run_id, event_type, metric_value, payload_json, created_at
                FROM content_metrics WHERE created_at >= ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (since, max(1, limit)),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d.pop("payload_json") or "{}")
            except Exception:
                d["payload"] = {}
            out.append(d)
        return out
    finally:
        conn.close()


def alert_was_sent_recently(dedupe_key: str, *, within_sec: int = 3600) -> bool:
    init_storage()
    since = _now() - max(60, within_sec)
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT sent_ts FROM alert_sent_log WHERE dedupe_key=? AND sent_ts >= ?",
            (dedupe_key, since),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def record_alert_sent(*, dedupe_key: str, run_id: str, alert_type: str, sent_ts: int | None = None) -> None:
    init_storage()
    ts = int(sent_ts or _now())
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO alert_sent_log (dedupe_key, run_id, alert_type, sent_ts)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(dedupe_key) DO UPDATE SET sent_ts=excluded.sent_ts, run_id=excluded.run_id, alert_type=excluded.alert_type
            """,
            (dedupe_key, run_id, alert_type, ts),
        )
        conn.commit()
    finally:
        conn.close()


def count_alert_sent_log() -> int:
    init_storage()
    conn = _connect()
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM alert_sent_log").fetchone()
        return int(row["c"] if row else 0)
    finally:
        conn.close()


def purge_expired_alert_logs(*, older_than_sec: int) -> dict[str, int]:
    """删除 sent_ts 早于 retention 窗口的去重记录。"""
    init_storage()
    cutoff = _now() - max(3600, int(older_than_sec))
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM alert_sent_log WHERE sent_ts < ?", (cutoff,))
        conn.commit()
        return {"deleted": int(cur.rowcount or 0), "cutoff_ts": cutoff}
    finally:
        conn.close()


