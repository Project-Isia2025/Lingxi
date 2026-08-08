"""编排路由说明 — 生产主路径 vs LangGraph 实验路径。"""
from __future__ import annotations

import os
from typing import Any

PRODUCTION_PATH = "orchestrator_agent"
EXPERIMENTAL_PATH = "langgraph"


def langgraph_enabled() -> bool:
    return os.environ.get("LANGGRAPH_ORCHESTRATOR_ENABLED", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def orchestrator_routing_info() -> dict[str, Any]:
    return {
        "ok": True,
        "production_path": PRODUCTION_PATH,
        "production_entry": {
            "module": "orchestrator.orchestrator_agent",
            "api": "POST /api/orchestrator/run",
            "cli": "python cli.py",
            "agents": "orchestrator/*_agent.py (sync run(ctx))",
            "features": ["五层矩阵", "Replan", "矩阵发布", "人工决策队列"],
        },
        "experimental_path": EXPERIMENTAL_PATH,
        "experimental_entry": {
            "module": "orchestrator.graph",
            "api": "POST /api/orchestrator/langgraph/run",
            "cli": "python main.py",
            "agents": "agents/* (async execute)",
            "enabled": langgraph_enabled(),
            "status": "experimental",
            "note": "与生产路径 Agent 实现分离；验证新特性后再考虑收敛",
        },
        "recommendation": (
            "运营/发布/投流请使用 POST /api/orchestrator/run；"
            "LangGraph 仅用于架构实验与 Campaign API。"
        ),
    }
