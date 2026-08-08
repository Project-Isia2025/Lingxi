"""工作流共享上下文：各 Agent 读写同一 WorkflowContext。"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowGoal:
    """用户目标输入。"""

    title: str = ""
    keyword: str = ""
    platform: str = "douyin"
    industry: str = ""
    org_id: str = ""
    byok_client_id: str = ""
    budget_limit: float = 0.0
    auto_execute: bool = False
    auto_publish: bool = False
    auto_matrix_publish: bool = False
    video_path: str = ""
    reference_urls: list[str] = field(default_factory=list)
    min_likes: int = 0
    min_followers: int = 0
    min_like_rate: float = 0.0
    discover_limit: int = 15
    video_provider: str = ""
    poll_task_completion: bool = False
    task_poll_timeout_sec: float = 900
    auto_publish_preview: bool = True
    enable_replan: bool = False
    max_iterations: int = 2
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentEvent:
    agent: str
    phase: str
    status: str
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


@dataclass
class WorkflowContext:
    """单次工作流运行的共享黑板。"""

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    goal: WorkflowGoal = field(default_factory=WorkflowGoal)
    stage: str = "init"
    status: str = "pending"
    error: str = ""
    roi_score: float = 0.0
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    events: list[AgentEvent] = field(default_factory=list)

    perception: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    strategy: dict[str, Any] = field(default_factory=dict)
    content: dict[str, Any] = field(default_factory=dict)
    execution: dict[str, Any] = field(default_factory=dict)
    plan: dict[str, Any] = field(default_factory=dict)

    def log(
        self,
        agent: str,
        phase: str,
        status: str,
        message: str = "",
        **payload: Any,
    ) -> None:
        self.events.append(
            AgentEvent(
                agent=agent,
                phase=phase,
                status=status,
                message=message,
                payload=dict(payload),
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "stage": self.stage,
            "status": self.status,
            "error": self.error,
            "roi_score": round(self.roi_score, 3),
            "conflicts": self.conflicts,
            "goal": {
                "title": self.goal.title,
                "keyword": self.goal.keyword,
                "platform": self.goal.platform,
                "industry": self.goal.industry,
                "org_id": self.goal.org_id,
                "budget_limit": self.goal.budget_limit,
                "auto_execute": self.goal.auto_execute,
                "auto_publish": self.goal.auto_publish,
                "auto_matrix_publish": self.goal.auto_matrix_publish,
                "video_path": self.goal.video_path,
                "reference_urls": self.goal.reference_urls,
                "enable_replan": self.goal.enable_replan,
                "max_iterations": self.goal.max_iterations,
            },
            "plan": self.plan,
            "perception": self.perception,
            "memory": self.memory,
            "strategy": self.strategy,
            "content": self.content,
            "execution": self.execution,
            "events": [
                {
                    "agent": e.agent,
                    "phase": e.phase,
                    "status": e.status,
                    "message": e.message,
                    "payload": e.payload,
                    "ts": e.ts,
                }
                for e in self.events
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowContext:
        goal_raw = data.get("goal") or {}
        goal = WorkflowGoal(
            title=str(goal_raw.get("title") or ""),
            keyword=str(goal_raw.get("keyword") or ""),
            platform=str(goal_raw.get("platform") or "douyin"),
            industry=str(goal_raw.get("industry") or ""),
            org_id=str(goal_raw.get("org_id") or ""),
            budget_limit=float(goal_raw.get("budget_limit") or 0),
            auto_execute=bool(goal_raw.get("auto_execute")),
            auto_publish=bool(goal_raw.get("auto_publish")),
            auto_matrix_publish=bool(goal_raw.get("auto_matrix_publish")),
            video_path=str(goal_raw.get("video_path") or ""),
            reference_urls=list(goal_raw.get("reference_urls") or []),
            enable_replan=bool(goal_raw.get("enable_replan")),
            max_iterations=int(goal_raw.get("max_iterations") or 2),
        )
        events = []
        for e in data.get("events") or []:
            if not isinstance(e, dict):
                continue
            events.append(
                AgentEvent(
                    agent=str(e.get("agent") or ""),
                    phase=str(e.get("phase") or ""),
                    status=str(e.get("status") or ""),
                    message=str(e.get("message") or ""),
                    payload=dict(e.get("payload") or {}),
                    ts=float(e.get("ts") or time.time()),
                )
            )
        return cls(
            run_id=str(data.get("run_id") or ""),
            goal=goal,
            stage=str(data.get("stage") or "init"),
            status=str(data.get("status") or "pending"),
            error=str(data.get("error") or ""),
            roi_score=float(data.get("roi_score") or 0),
            conflicts=list(data.get("conflicts") or []),
            events=events,
            perception=dict(data.get("perception") or {}),
            memory=dict(data.get("memory") or {}),
            strategy=dict(data.get("strategy") or {}),
            content=dict(data.get("content") or {}),
            execution=dict(data.get("execution") or {}),
            plan=dict(data.get("plan") or {}),
        )
