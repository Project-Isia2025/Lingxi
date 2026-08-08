"""总控大脑 — 基于 LangGraph 的多 Agent 编排。

与 orchestrator.orchestrator_agent.OrchestratorAgent（五层+记忆+Replan）并存：
- Orchestrator       -> LangGraph 状态图（本模块）
- OrchestratorAgent  -> 原有工作流（CLI /api/orchestrator/run）
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from orchestrator.nodes import OrchestratorNodes
from orchestrator.state import GlobalState, build_initial_state


class Orchestrator:
    """LangGraph 总控大脑。"""

    NODE_SEQUENCE = (
        "perceive",
        "analyze_strategy",
        "arbitrate",
        "create_content",
        "execute",
        "monitor_roi",
    )

    def __init__(self) -> None:
        self.nodes = OrchestratorNodes()
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(GlobalState)
        n = self.nodes

        workflow.add_node("perceive", n.perceive)
        workflow.add_node("analyze_strategy", n.analyze_strategy)
        workflow.add_node("create_content", n.create_content)
        workflow.add_node("execute", n.execute)
        workflow.add_node("monitor_roi", n.monitor_roi)
        workflow.add_node("arbitrate", n.arbitrate)

        workflow.set_entry_point("perceive")
        workflow.add_edge("perceive", "analyze_strategy")
        workflow.add_conditional_edges(
            "analyze_strategy",
            n.needs_approval,
            {True: "arbitrate", False: "create_content"},
        )
        workflow.add_edge("arbitrate", "create_content")
        workflow.add_edge("create_content", "execute")
        workflow.add_edge("execute", "monitor_roi")
        workflow.add_conditional_edges(
            "monitor_roi",
            n.should_continue,
            {True: "perceive", False: END},
        )

        return workflow.compile()

    async def run(self, initial_state: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
        state = initial_state or build_initial_state(**kwargs)
        return await self.graph.ainvoke(state)

    def graph_info(self) -> dict[str, Any]:
        return {
            "engine": "langgraph",
            "nodes": list(self.NODE_SEQUENCE),
            "entry": "perceive",
            "loop": "monitor_roi -> perceive (when ROI>1 and budget left)",
        }


async def run_langgraph_orchestrator(**kwargs) -> dict[str, Any]:
    """便捷入口 — 供 API / 脚本调用。"""
    orch = Orchestrator()
    return await orch.run(**kwargs)
