"""Agent 基类与统一返回结构。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from orchestrator.context import WorkflowContext


@dataclass
class AgentResult:
    ok: bool
    agent: str
    phase: str
    data: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    roi_delta: float = 0.0
    conflicts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "agent": self.agent,
            "phase": self.phase,
            "message": self.message,
            "roi_delta": self.roi_delta,
            "conflicts": self.conflicts,
            "data": self.data,
        }


class BaseAgent(ABC):
    name: str = "base"
    phase: str = "unknown"

    @abstractmethod
    def run(self, ctx: WorkflowContext) -> AgentResult:
        raise NotImplementedError
