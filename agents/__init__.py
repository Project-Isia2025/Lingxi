"""四个子 Agent 统一注册与导出。"""
from __future__ import annotations

from agents.base import AgentState, BaseAgent
from agents.content import ContentAgent
from agents.execution import ExecutionAgent
from agents.perception import PerceptionAgent
from agents.strategy import StrategyAgent

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "perception": PerceptionAgent,
    "strategy": StrategyAgent,
    "content": ContentAgent,
    "execution": ExecutionAgent,
}


def get_agent(name: str) -> BaseAgent:
    cls = AGENT_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"unknown agent: {name}")
    return cls()


def list_agents() -> list[str]:
    return list(AGENT_REGISTRY.keys())


__all__ = [
    "BaseAgent",
    "AgentState",
    "PerceptionAgent",
    "StrategyAgent",
    "ContentAgent",
    "ExecutionAgent",
    "AGENT_REGISTRY",
    "get_agent",
    "list_agents",
]

from agents.pipeline import run_pipeline

__all__.append("run_pipeline")
