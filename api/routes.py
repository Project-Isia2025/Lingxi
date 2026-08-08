"""Campaign API — Phase 7 指南规范 FastAPI 应用。



独立运行于端口 8000:

  uvicorn api.routes:app --host 0.0.0.0 --port 8000



与 api_server.py（9200 五层矩阵 API）并存；Campaign 路由已同时挂载在 9200。

"""

from __future__ import annotations



import bootstrap



bootstrap.ensure_paths()

bootstrap.load_local_env()



from fastapi import FastAPI



from api.endpoints.campaign import router as campaign_router

from api.schemas import HealthResponse



app = FastAPI(

    title="Content Commerce Agent API",

    description="Phase 7 指南规范 Campaign API",

    version="1.0.0",

)

app.include_router(campaign_router)





@app.get("/health", response_model=HealthResponse)

async def health():

    checks = {}

    try:

        from orchestrator.graph import Orchestrator



        checks["langgraph"] = Orchestrator().graph_info()

    except Exception as exc:

        checks["langgraph"] = {"ok": False, "error": str(exc)}

    try:

        from agents import list_agents



        checks["agents"] = list_agents()

    except Exception as exc:

        checks["agents"] = {"ok": False, "error": str(exc)}

    ok = "langgraph" in checks and isinstance(checks.get("langgraph"), dict)

    return HealthResponse(status="healthy" if ok else "degraded", checks=checks)





@app.get("/")

def root():

    return {

        "service": "Content Commerce Agent API",

        "dashboard": "http://127.0.0.1:9200/dashboard",

        "docs": "/docs",

        "health": "/health",

        "start": "POST /campaigns/start",

    }


