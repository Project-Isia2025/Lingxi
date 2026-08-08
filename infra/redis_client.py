"""Redis 连接与消息总线。"""
from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

import redis.asyncio as redis


def _redis_kwargs() -> dict[str, Any]:
    return {
        "host": os.environ.get("REDIS_HOST", "localhost"),
        "port": int(os.environ.get("REDIS_PORT", "6379")),
        "decode_responses": True,
        "socket_connect_timeout": float(os.environ.get("REDIS_CONNECT_TIMEOUT", "0.5")),
        "socket_timeout": float(os.environ.get("REDIS_SOCKET_TIMEOUT", "0.5")),
    }


redis_client = redis.Redis(**_redis_kwargs())


class MessageBus:
    """Agent 间通信 — Redis Streams。"""

    def __init__(self, client: redis.Redis | None = None):
        self.redis = client or redis_client

    async def publish(self, channel: str, message: dict) -> str:
        flat = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in message.items()}
        return await self.redis.xadd(channel, flat)

    async def subscribe(self, channel: str, consumer: str = "default") -> AsyncIterator[dict]:
        last_id = "$"
        while True:
            entries = await self.redis.xread({channel: last_id}, block=1000, count=10)
            for _stream, messages in entries or []:
                for msg_id, fields in messages:
                    last_id = msg_id
                    yield {"id": msg_id, **fields}
