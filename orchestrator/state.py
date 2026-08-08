"""LangGraph 全局状态定义。"""
from __future__ import annotations

import uuid
from typing import Annotated, Any, TypedDict

try:
    from langgraph.graph.message import add_messages
except ImportError:

    def add_messages(left, right):  # type: ignore[misc]
        return (left or []) + (right or [])


class GlobalState(TypedDict, total=False):
    # 任务目标
    goal: str
    platform: str
    sub_tasks: list[dict]

    # 各 Agent 输出
    perception_data: dict
    strategy_data: dict
    content_data: dict
    execution_data: dict

    # ROI 追踪
    total_budget: float
    total_spend: float
    total_revenue: float
    current_roi: float

    # 运行控制
    run_id: str
    status: str
    max_iterations: int
    materials: list[str]

    # 系统状态
    messages: Annotated[list, add_messages]
    pending_approvals: list[dict]
    errors: list[str]
    iteration: int


def build_initial_state(
    *,
    goal: str,
    platform: str = "douyin",
    total_budget: float = 5000.0,
    materials: list[str] | None = None,
    max_iterations: int = 10,
    run_id: str | None = None,
) -> dict[str, Any]:
    """构造 LangGraph 初始状态。"""
    return {
        "goal": goal,
        "platform": platform,
        "total_budget": float(total_budget),
        "total_spend": 0.0,
        "total_revenue": 0.0,
        "current_roi": 0.0,
        "iteration": 0,
        "max_iterations": max_iterations,
        "run_id": run_id or str(uuid.uuid4()),
        "status": "running",
        "messages": [],
        "pending_approvals": [],
        "errors": [],
        "materials": materials or [],
        "sub_tasks": [],
    }
