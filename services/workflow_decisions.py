"""工作流人工决策队列 — 预算、出价等关键决策。"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

import bootstrap

_DECISION_META: dict[str, dict[str, str]] = {
    "budget_over_limit": {
        "type_label": "制作预算确认",
        "hint": "AI 估算制作成本超出预算。您点头后 AI 自动改用经济方案继续；拒绝则终止任务。",
    },
    "ad_budget_high": {
        "type_label": "投流预算确认",
        "hint": "AI 建议加大投流预算。您点头后 AI 自动执行；拒绝则终止任务。",
    },
    "high_bid": {
        "type_label": "出价加价确认",
        "hint": "AI 建议提高 CPC 出价抢量。您点头后 AI 自动执行；拒绝则终止任务。",
    },
}

_HUMAN_TYPES = frozenset(_DECISION_META.keys())


def human_decision_types() -> frozenset[str]:
    return _HUMAN_TYPES


def _db_path():
    import os
    from pathlib import Path

    raw = os.environ.get("MATRIX_DB_PATH", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return bootstrap.project_root() / "data" / "matrix_agent.db"


def _connect():
    import sqlite3

    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table() -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_decisions (
                decision_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                decision_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                title TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_ts INTEGER NOT NULL DEFAULT 0,
                resolved_ts INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_workflow_decisions_pending
            ON workflow_decisions(status, created_ts DESC)
            """
        )
        conn.commit()
    finally:
        conn.close()


def _format_summary(conflict: dict[str, Any], *, goal_keyword: str = "") -> str:
    ctype = str(conflict.get("type") or "")
    if ctype == "budget_over_limit":
        est = conflict.get("estimated_cost")
        selected = conflict.get("selected") or conflict.get("fallback_provider") or "template"
        return f"推广「{goal_keyword}」的视频制作预估 {est} 元，超出预算。AI 建议改用「{selected}」方案继续。"
    if ctype == "ad_budget_high":
        daily = conflict.get("daily_budget_cny")
        limit = conflict.get("budget_limit")
        return f"AI 建议日投流 {daily} 元，高于您设定的总预算 {limit} 元。"
    if ctype == "high_bid":
        bid = conflict.get("bid_cpc")
        daily = conflict.get("daily_budget_cny")
        extra = f"，日预算约 {daily} 元" if daily else ""
        return f"AI 建议 CPC 出价 {bid} 元/点击，高于常规安全线（2 元）{extra}。"
    return str(conflict.get("message") or "需要您确认是否继续")


def create_from_conflict(*, run_id: str, conflict: dict[str, Any], goal_keyword: str = "") -> dict[str, Any]:
    ctype = str(conflict.get("type") or "")
    if ctype not in _HUMAN_TYPES:
        return {"ok": False, "error": "not_human_decision"}
    _ensure_table()
    decision_id = f"dec-{uuid.uuid4().hex[:12]}"
    meta = _DECISION_META.get(ctype, {})
    title = {
        "budget_over_limit": "视频制作超预算",
        "ad_budget_high": "投流预算偏高",
        "high_bid": "CPC 出价偏高",
    }.get(ctype, "策略确认")
    row = {
        "decision_id": decision_id,
        "run_id": run_id,
        "decision_type": ctype,
        "status": "pending",
        "title": title,
        "summary": _format_summary(conflict, goal_keyword=goal_keyword),
        "payload": dict(conflict),
        "created_ts": int(time.time()),
    }
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO workflow_decisions
            (decision_id, run_id, decision_type, status, title, summary, payload_json, created_ts)
            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)
            """,
            (
                decision_id,
                run_id,
                ctype,
                title,
                row["summary"],
                json.dumps(row["payload"], ensure_ascii=False),
                row["created_ts"],
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, **row}


def list_pending(*, limit: int = 20) -> list[dict[str, Any]]:
    _ensure_table()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT decision_id, run_id, decision_type, status, title, summary, payload_json, created_ts
            FROM workflow_decisions
            WHERE status='pending'
            ORDER BY created_ts DESC
            LIMIT ?
            """,
            (max(1, min(limit, 100)),),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            ctype = r["decision_type"]
            meta = _DECISION_META.get(ctype, {})
            payload = {}
            try:
                payload = json.loads(r["payload_json"] or "{}")
            except Exception:
                payload = {}
            out.append(
                {
                    "decision_id": r["decision_id"],
                    "type": ctype,
                    "type_label": meta.get("type_label", "策略确认"),
                    "title": r["title"],
                    "summary": r["summary"],
                    "run_id": r["run_id"],
                    "hint": meta.get("hint", ""),
                    "payload": payload,
                    "actions": [
                        {"id": "approve", "label": "点头通过", "style": "primary"},
                        {"id": "reject", "label": "拒绝终止", "style": "danger"},
                    ],
                }
            )
        return out
    finally:
        conn.close()


def get_decision(decision_id: str) -> dict[str, Any] | None:
    _ensure_table()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM workflow_decisions WHERE decision_id=?",
            (decision_id,),
        ).fetchone()
        if not row:
            return None
        payload = {}
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except Exception:
            payload = {}
        return {
            "decision_id": row["decision_id"],
            "run_id": row["run_id"],
            "decision_type": row["decision_type"],
            "status": row["status"],
            "title": row["title"],
            "summary": row["summary"],
            "payload": payload,
        }
    finally:
        conn.close()


def _mark_decision(decision_id: str, status: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE workflow_decisions SET status=?, resolved_ts=? WHERE decision_id=?",
            (status, int(time.time()), decision_id),
        )
        conn.commit()
    finally:
        conn.close()


def apply_approval(ctx_dict: dict[str, Any], conflict: dict[str, Any]) -> dict[str, Any]:
    """将人工批准应用到工作流上下文。"""
    ctype = str(conflict.get("type") or "")
    strategy = dict(ctx_dict.get("strategy") or {})
    goal = dict(ctx_dict.get("goal") or {})

    if ctype == "budget_over_limit":
        selected = conflict.get("selected") or conflict.get("fallback_provider") or "template"
        strategy["selected_provider"] = selected
        cost = dict(strategy.get("video_cost_plan") or {})
        cost["selected_provider"] = selected
        cost["human_approved_downgrade"] = True
        strategy["video_cost_plan"] = cost
    elif ctype == "ad_budget_high":
        ad_plan = dict(strategy.get("ad_plan") or {})
        ad_plan["human_approved_budget"] = True
        strategy["ad_plan"] = ad_plan
    elif ctype == "high_bid":
        bidding = dict(strategy.get("bidding") or {})
        bidding["bid_cpc"] = float(conflict.get("bid_cpc") or bidding.get("bid_cpc") or 2.0)
        bidding["human_approved"] = True
        strategy["bidding"] = bidding
        ad_plan = dict(strategy.get("ad_plan") or {})
        ad_plan["approved_bid_cpc"] = bidding["bid_cpc"]
        strategy["ad_plan"] = ad_plan

    ctx_dict["strategy"] = strategy
    conflicts = list(ctx_dict.get("conflicts") or [])
    for c in conflicts:
        if str(c.get("type") or "") == ctype:
            c["resolution"] = {"action": "human_approved"}
    ctx_dict["conflicts"] = conflicts
    return ctx_dict


def apply_rejection(ctx_dict: dict[str, Any], *, reason: str) -> dict[str, Any]:
    ctx_dict["status"] = "cancelled"
    ctx_dict["stage"] = "done"
    ctx_dict["error"] = reason or "用户拒绝策略方案"
    return ctx_dict


def resolve_decision(*, decision_id: str, approved: bool, reason: str = "") -> dict[str, Any]:
    item = get_decision(decision_id)
    if not item:
        return {"ok": False, "error": "decision_not_found"}
    if item["status"] != "pending":
        return {"ok": False, "error": "already_resolved", "status": item["status"]}

    from orchestrator.workflow_store import load_run, save_run

    run_id = str(item["run_id"] or "")
    ctx_dict = load_run(run_id)
    if not ctx_dict:
        return {"ok": False, "error": "run_not_found"}

    if approved:
        ctx_dict = apply_approval(ctx_dict, item["payload"])
        ctx_dict["status"] = "running"
        ctx_dict["stage"] = "content"
        plan = dict(ctx_dict.get("plan") or {})
        plan["resume_from"] = 3
        ctx_dict["plan"] = plan
        _mark_decision(decision_id, "approved")
        save_run(ctx_dict)
        from orchestrator.orchestrator_agent import resume_workflow

        resume_workflow(run_id)
        delete_decision(decision_id)
        return {
            "ok": True,
            "decision_id": decision_id,
            "run_id": run_id,
            "message": "已确认，AI 将继续自动执行内容制作与发布",
        }

    ctx_dict = apply_rejection(ctx_dict, reason=reason or "您拒绝了 AI 的策略建议")
    _mark_decision(decision_id, "rejected")
    save_run(ctx_dict)
    delete_decision(decision_id)
    return {
        "ok": True,
        "decision_id": decision_id,
        "run_id": run_id,
        "message": "已拒绝，本任务已终止",
        "status": "cancelled",
    }


def delete_decision(decision_id: str) -> bool:
    _ensure_table()
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM workflow_decisions WHERE decision_id=?", (decision_id,))
        conn.commit()
        return int(cur.rowcount or 0) > 0
    finally:
        conn.close()


def purge_resolved_decisions(*, older_than_sec: int) -> dict[str, int]:
    _ensure_table()
    cutoff = int(time.time()) - max(0, int(older_than_sec))
    conn = _connect()
    try:
        cur = conn.execute(
            """
            DELETE FROM workflow_decisions
            WHERE status IN ('approved', 'rejected')
              AND COALESCE(NULLIF(resolved_ts, 0), created_ts) < ?
            """,
            (cutoff,),
        )
        conn.commit()
        return {"deleted": int(cur.rowcount or 0), "cutoff_ts": cutoff}
    finally:
        conn.close()
