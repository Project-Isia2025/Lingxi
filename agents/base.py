"""所有 Agent 的基类。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

try:
    import structlog

    logger = structlog.get_logger()
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    agent_name: str
    status: str = "idle"
    last_run: datetime | None = None
    results: dict = field(default_factory=dict)


class BaseAgent(ABC):
    def __init__(self, name: str) -> None:
        self.name = name
        self.state = AgentState(agent_name=name)
        try:
            self.logger = structlog.get_logger().bind(agent=name)
        except Exception:
            self.logger = logger

    @abstractmethod
    async def execute(self, task: dict) -> dict:
        raise NotImplementedError

    async def run(self, task: dict) -> dict:
        self.state.status = "running"
        self.state.last_run = datetime.now()
        try:
            self.logger.info("task_started", task=task)
            result = await self.execute(task)
            self.state.status = "idle"
            self.state.results = result
            self.logger.info("task_completed", result_keys=list(result.keys()))
            return result
        except Exception as e:
            self.state.status = "error"
            self.logger.error("task_failed", error=str(e))
            raise
