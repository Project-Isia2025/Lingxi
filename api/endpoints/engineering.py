"""工程师技术栈 API + 对照页。"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pathlib import Path

import bootstrap

bootstrap.ensure_paths()

from api.auth import inject_auth_script

router = APIRouter(tags=["engineering"])

_ENGINEERING_HTML = inject_auth_script(Path(__file__).with_name("engineering_stack.html").read_text(encoding="utf-8"))


@router.get("/api/engineering/stack")
def engineering_stack_api():
    from services.engineering_stack import build_engineering_stack

    return build_engineering_stack()


@router.get("/api/engineering/llm")
def engineering_llm_status():
    from services.llm_router import llm_router_status

    return llm_router_status()


@router.get("/dashboard/engineering", response_class=HTMLResponse)
def engineering_dashboard():
    return HTMLResponse(_ENGINEERING_HTML)
