"""📦 记忆与知识库 Agent（独立实现）。"""
from __future__ import annotations

from orchestrator.base import AgentResult, BaseAgent
from orchestrator.context import WorkflowContext
from services.knowledge import retrieve_memory


class MemoryAgent(BaseAgent):
    name = "memory"
    phase = "memory"

    def run(self, ctx: WorkflowContext) -> AgentResult:
        goal = ctx.goal
        keyword = (goal.keyword or goal.title or goal.industry or "").strip()
        platform = (goal.platform or "douyin").strip().lower()

        memory_out = retrieve_memory(
            query=keyword,
            title=goal.title or keyword,
            platform=platform,
            perception=ctx.perception or {},
        )
        ctx.memory = memory_out
        from services.knowledge import save_agent_episode

        save_agent_episode(
            run_id=ctx.run_id,
            agent=self.name,
            observation=f"召回 {len(memory_out.get('sop_entries') or [])} 条 SOP",
            action="retrieve_memory",
            payload={"query": keyword},
        )
        ctx.log(
            self.name,
            self.phase,
            "ok",
            f"素材 {len(memory_out.get('sop_entries') or [])} 条",
        )
        return AgentResult(
            ok=True,
            agent=self.name,
            phase=self.phase,
            data=memory_out,
            message="记忆库已加载",
            roi_delta=0.08,
        )
