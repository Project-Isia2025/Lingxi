"""Agent 工作流驾驶舱 — AI 感知·决策·执行，人类点头确认与应急兜底。"""
from __future__ import annotations

import time
from typing import Any

PLATFORM_LABEL = {
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "xhs": "小红书",
    "shipinhao": "视频号",
    "weixin": "视频号",
}

PHILOSOPHY = {
    "summary": "AI 负责感知、决策、执行；人类负责点头确认与应急兜底",
    "ai": [
        {
            "id": "perceive",
            "role": "感知",
            "subtitle": "看数据",
            "desc": "自动采集竞品、热点、历史经验与市场波动",
            "agents": ["感知 Agent", "记忆 Agent"],
        },
        {
            "id": "decide",
            "role": "决策",
            "subtitle": "定策略",
            "desc": "自动选品定价、投流方案与持续优化重规划",
            "agents": ["策略 Agent", "总控 Replan"],
        },
        {
            "id": "execute",
            "role": "执行",
            "subtitle": "发任务",
            "desc": "自动生成内容、质检发布、投流与效果跟踪",
            "agents": ["内容 Agent", "执行 Agent"],
        },
    ],
    "human": [
        {
            "id": "confirm",
            "role": "点头确认",
            "desc": "仅在超预算、加价、成片发布等关键节点暂停，等您一键确认",
        },
        {
            "id": "fallback",
            "role": "应急兜底",
            "desc": "系统异常或 AI 卡住时，人工介入取消、重试或查看状态",
        },
    ],
}

MACRO_PIPELINE: list[dict[str, Any]] = [
    {"id": "perceive", "label": "感知", "icon": "📡", "stages": {"planning", "perception", "memory", "perceived"}},
    {"id": "decide", "label": "决策", "icon": "♟️", "stages": {"strategy", "awaiting_decision", "observe", "replan", "strategy_ready", "arbitrated"}},
    {"id": "execute", "label": "执行", "icon": "🚀", "stages": {"content", "execution", "awaiting_review", "content_ready", "executed", "optimizing", "completed"}},
]

STATUS_LABEL = {    "pending": "排队中",
    "running": "AI 自动运行中",
    "completed": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
    "awaiting_decision": "等您点头（策略）",
    "awaiting_review": "等您点头（成片）",
    "pending_review": "等您点头（成片）",
}
AGENT_PIPELINE: list[dict[str, str]] = [
    {"id": "planning", "agent": "总控", "label": "任务拆解", "desc": "AI 分解推广目标"},
    {"id": "perception", "agent": "感知 Agent", "label": "市场感知", "desc": "分析竞品与热点"},
    {"id": "memory", "agent": "记忆 Agent", "label": "经验检索", "desc": "调取知识与规范"},
    {"id": "strategy", "agent": "策略 Agent", "label": "策略制定", "desc": "选品、定价、投流方案"},
    {"id": "content", "agent": "内容 Agent", "label": "内容生产", "desc": "脚本与视频生成"},
    {"id": "execution", "agent": "执行 Agent", "label": "执行发布", "desc": "质检、发布、投流"},
    {"id": "observe", "agent": "总控", "label": "效果观察", "desc": "分析投放数据"},
    {"id": "replan", "agent": "总控", "label": "自动优化", "desc": "AI 重规划并迭代"},
    {"id": "awaiting_decision", "agent": "您", "label": "策略确认", "desc": "预算/出价需您拍板"},
    {"id": "awaiting_review", "agent": "您", "label": "成片确认", "desc": "视频需您确认发布"},
    {"id": "done", "agent": "总控", "label": "完成", "desc": "本轮工作流结束"},
]

_STAGE_ORDER = [s["id"] for s in AGENT_PIPELINE]


def _stage_index(stage: str) -> int:
    st = (stage or "").strip().lower()
    if st in _STAGE_ORDER:
        return _STAGE_ORDER.index(st)
    if st == "done":
        return len(_STAGE_ORDER) - 1
    return 0


def _build_macro_progress(stage: str, status: str) -> list[dict[str, Any]]:
    """三大 AI 职责进度 — 面向运营者。"""
    st = (stage or "").strip().lower()
    if status in ("awaiting_decision",):
        active_id = "decide"
    elif status in ("awaiting_review", "pending_review"):
        active_id = "execute"
    elif status == "completed":
        active_id = "execute"
    else:
        active_id = "perceive"
        for pillar in MACRO_PIPELINE:
            if st in pillar["stages"]:
                active_id = pillar["id"]
                break
        if st in {"observe", "replan"}:
            active_id = "decide"
        if st in {"content", "execution"}:
            active_id = "execute"

    order = [p["id"] for p in MACRO_PIPELINE]
    active_idx = order.index(active_id) if active_id in order else 0
    rows: list[dict[str, Any]] = []
    for i, pillar in enumerate(MACRO_PIPELINE):
        if status == "completed":
            state = "done"
        elif status in ("failed", "cancelled") and i == active_idx:
            state = "error"
        elif i < active_idx:
            state = "done"
        elif i == active_idx:
            state = "active"
        else:
            state = "pending"
        if status in ("awaiting_decision",) and pillar["id"] == "decide":
            state = "wait_human"
        if status in ("awaiting_review", "pending_review") and pillar["id"] == "execute":
            state = "wait_human"
        rows.append({**pillar, "state": state})
    return rows


def _build_pipeline_progress(stage: str, status: str) -> list[dict[str, Any]]:
    current = _stage_index(stage)
    if status in ("completed", "failed", "cancelled") and stage != "done":
        current = len(_STAGE_ORDER) - 1 if status == "completed" else current
    rows: list[dict[str, Any]] = []
    for i, step in enumerate(AGENT_PIPELINE):
        if status == "completed" and step["id"] != "done":
            state = "done"
        elif status in ("failed", "cancelled") and i == current:
            state = "error"
        elif i < current:
            state = "done"
        elif i == current:
            state = "active"
        else:
            state = "pending"
        rows.append({**step, "state": state})
    return rows


def _summarize_run(row: dict[str, Any], *, full: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = full or {}
    goal = payload.get("goal") or {}
    keyword = str(goal.get("keyword") or goal.get("title") or "").strip() or "推广任务"
    platform = str(goal.get("platform") or "douyin")
    stage = str(payload.get("stage") or row.get("stage") or "planning")
    status = str(payload.get("status") or row.get("status") or "pending")
    execution = payload.get("execution") or {}
    review = execution.get("review") or {}
    if review.get("ok") and review.get("status") == "pending_review":
        status = "awaiting_review"
    elif review.get("ok") and status == "running":
        status = "awaiting_review"
    elif status == "awaiting_decision":
        stage = "awaiting_decision"

    return {
        "run_id": row.get("run_id") or payload.get("run_id"),
        "title": keyword,
        "platform": platform,
        "platform_label": PLATFORM_LABEL.get(platform, platform),
        "stage": stage,
        "stage_label": next((s["label"] for s in AGENT_PIPELINE if s["id"] == stage), stage),
        "status": status,
        "status_label": STATUS_LABEL.get(status, status),
        "roi_score": payload.get("roi_score"),
        "updated_ts": row.get("updated_ts"),
        "pipeline": _build_pipeline_progress(stage, status),
        "macro_pipeline": _build_macro_progress(stage, status),
        "awaiting_human": status in ("awaiting_review", "pending_review", "awaiting_decision"),        "error": payload.get("error") or "",
    }


def _collect_decisions(*, limit: int = 10) -> tuple[list[dict[str, Any]], int]:
    from core.storage import list_review_queue
    from services.workflow_decisions import list_pending as list_strategy_decisions

    decisions: list[dict[str, Any]] = []
    pending_reviews = list_review_queue(status="pending_review", limit=500)
    pending_total = len(pending_reviews)

    for item in list_strategy_decisions(limit=limit):
        decisions.append(item)

    from services.feishu_review import review_token

    for item in pending_reviews[:limit]:
        script = str(item.get("script") or "").strip()
        preview = script[:120] + ("…" if len(script) > 120 else "")
        rid = str(item.get("review_id") or "")
        decisions.append(
            {
                "decision_id": rid,
                "type": "content_review",
                "type_label": "成片确认",
                "title": str(item.get("title") or "AI 生成的推广视频"),
                "summary": preview or "AI 已完成视频制作，请您确认是否发布",
                "run_id": item.get("run_id"),
                "video_path": item.get("video_path"),
                "token": review_token(rid),
                "actions": [
                    {"id": "approve", "label": "点头通过", "style": "primary"},
                    {"id": "reject", "label": "打回修改", "style": "danger"},
                ],
                "hint": "AI 已完成视频制作；您点头后 AI 自动发布并继续优化，无需其他操作",
            }
        )
    return decisions, pending_total


def build_workflow_overview(*, limit: int = 8) -> dict[str, Any]:
    from orchestrator.orchestrator_agent import _ACTIVE
    from orchestrator.workflow_store import list_runs, load_run

    raw_runs = list_runs(limit=limit)
    active: list[dict[str, Any]] = []
    recent: list[dict[str, Any]] = []

    for row in raw_runs:
        full = load_run(str(row.get("run_id") or "")) or {}
        summary = _summarize_run(row, full=full)
        st = summary["status"]
        if st in ("running", "awaiting_review", "pending_review", "awaiting_decision") or str(row.get("run_id")) in _ACTIVE:
            active.append(summary)
        else:
            recent.append(summary)

    decisions, pending_review_total = _collect_decisions(limit=10)
    completed_runs_total = len([r for r in raw_runs if str(r.get("status") or "") in ("completed", "cancelled", "failed")])

    return {
        "ok": True,
        "philosophy": PHILOSOPHY,
        "tagline": PHILOSOPHY["summary"],
        "active_count": len(active),
        "decision_count": len(decisions),
        "pending_review_total": pending_review_total,
        "completed_runs_total": completed_runs_total,
        "pipeline_template": AGENT_PIPELINE,
        "macro_pipeline_template": MACRO_PIPELINE,
        "decisions": decisions,
        "active_runs": active,
        "recent_runs": recent[:6],
        "ai_pillars": PHILOSOPHY["ai"],
        "human_roles": PHILOSOPHY["human"],
        "agents": PHILOSOPHY["ai"],
        "ts": int(time.time()),
    }

def build_run_detail(run_id: str) -> dict[str, Any] | None:
    from orchestrator.workflow_store import load_run

    full = load_run(run_id)
    if not full:
        return None
    row = {
        "run_id": run_id,
        "stage": full.get("stage"),
        "status": full.get("status"),
        "updated_ts": int(time.time()),
    }
    summary = _summarize_run(row, full=full)
    events = full.get("events") or []
    timeline = [
        {
            "agent": e.get("agent"),
            "phase": e.get("phase"),
            "status": e.get("status"),
            "message": e.get("message"),
            "ts": e.get("ts"),
        }
        for e in events[-30:]
    ]
    return {
        "ok": True,
        **summary,
        "plan": full.get("plan") or {},
        "conflicts": full.get("conflicts") or [],
        "timeline": timeline,
        "execution": full.get("execution") or {},
        "content_preview": str((full.get("content") or {}).get("script") or "")[:500],
    }
