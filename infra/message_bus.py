"""消息总线 — Redis Streams（指南 Phase 0 独立模块）。"""
from __future__ import annotations

from infra.redis_client import MessageBus, redis_client

__all__ = ["MessageBus", "redis_client"]
