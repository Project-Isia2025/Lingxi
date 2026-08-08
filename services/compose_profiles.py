"""Docker Compose profile 定义与校验。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import bootstrap

COMPOSE_PROFILES: dict[str, dict[str, Any]] = {
    "default": {
        "label": "基础 API",
        "services": ["matrix-api"],
        "description": "仅启动 matrix-api:9100",
    },
    "playwright": {
        "label": "Playwright 发布/爬虫",
        "services": ["matrix-playwright"],
        "description": "Playwright 镜像 + 发布队列 Worker，端口 9101",
    },
    "tunnel": {
        "label": "Cloudflare 公网隧道",
        "services": ["matrix-tunnel"],
        "description": "cloudflared Quick Tunnel → matrix-api，日志中查看公网 URL",
    },
    "full": {
        "label": "完整栈",
        "services": ["matrix-api", "matrix-playwright", "matrix-tunnel"],
        "description": "API + Playwright + 公网隧道",
        "includes": ["playwright", "tunnel"],
    },
    "prod": {
        "label": "生产 Docker（叠加 prod override）",
        "services": ["matrix-api"],
        "description": "deploy/docker-compose.prod.yml 资源限制 + Worker 开关",
    },
    "prod-full": {
        "label": "生产完整栈",
        "services": ["matrix-api", "matrix-playwright", "matrix-tunnel"],
        "description": "生产 override + Playwright + 隧道",
        "includes": ["playwright", "tunnel"],
    },
}


def compose_file_path() -> Path:
    return bootstrap.project_root() / "docker-compose.yml"


def resolve_profiles(name: str) -> list[str]:
    """解析 stack 名称为 compose profile 列表。"""
    key = (name or "default").strip().lower()
    if key == "default" or not key:
        return []
    if key == "full":
        return ["playwright", "tunnel"]
    if key in ("prod-full", "full-prod", "production-full"):
        return ["playwright", "tunnel"]
    return [key]


def compose_status() -> dict[str, Any]:
    path = compose_file_path()
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    has_tunnel = "matrix-tunnel" in text
    has_playwright = "matrix-playwright" in text
    return {
        "ok": path.is_file(),
        "compose_file": str(path),
        "profiles": COMPOSE_PROFILES,
        "services_detected": {
            "matrix-api": "matrix-api" in text,
            "matrix-playwright": has_playwright,
            "matrix-tunnel": has_tunnel,
        },
        "full_stack_ready": has_tunnel and has_playwright,
        "up_hint": "python scripts/docker_up.py --stack full --build",
        "prod_hint": "python scripts/deploy_up.py --stack prod-full --build",
    }
