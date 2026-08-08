"""四个子 Agent — 统一 API。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentTaskRequest(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


@router.get("/")
def list_agents():
    from agents import list_agents as _list

    return {"agents": _list(), "supported": ["perception", "strategy", "content", "execution"]}


@router.get("/{agent_name}/status")
def agent_status(agent_name: str):
    from agents import get_agent

    try:
        agent = get_agent(agent_name)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {
        "name": agent.name,
        "status": agent.state.status,
        "last_run": agent.state.last_run.isoformat() if agent.state.last_run else None,
        "last_result_keys": list(agent.state.results.keys()) if agent.state.results else [],
    }


@router.post("/{agent_name}/run")
async def run_agent(agent_name: str, req: AgentTaskRequest):
    from agents import get_agent

    try:
        agent = get_agent(agent_name)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    task = {"type": req.type, **req.payload}
    try:
        result = await agent.run(task)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"ok": True, "agent": agent_name, "status": agent.state.status, "result": result}


@router.post("/pipeline/run")
async def run_pipeline_endpoint(body: dict[str, Any]):
    from agents.pipeline import run_pipeline

    return await run_pipeline(body)
