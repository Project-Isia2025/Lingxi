"""Redis 分布式 Leader Lock — 多副本 API 下仅一个实例跑后台任务。"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any

log = logging.getLogger(__name__)

_INSTANCE_ID = uuid.uuid4().hex[:12]
_TRUE = frozenset({"1", "true", "yes", "on"})


def leader_lock_enabled() -> bool:
    return os.environ.get("WORKER_LEADER_LOCK_ENABLED", "1").strip().lower() in _TRUE


def lock_ttl_sec() -> int:
    try:
        return max(30, int(os.environ.get("WORKER_LEADER_LOCK_TTL_SEC", "120")))
    except ValueError:
        return 120


def _redis_client():
    import redis

    return redis.Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        decode_responses=True,
        socket_connect_timeout=float(os.environ.get("REDIS_CONNECT_TIMEOUT", "0.5")),
        socket_timeout=float(os.environ.get("REDIS_SOCKET_TIMEOUT", "0.5")),
    )


def try_acquire_leader(lock_name: str, *, ttl_sec: int | None = None) -> bool:
    """尝试成为 named worker 的 leader；Redis 不可用时降级为单节点模式。"""
    if not leader_lock_enabled():
        return True

    ttl = int(ttl_sec or lock_ttl_sec())
    key = f"matrix:leader:{lock_name}"
    try:
        client = _redis_client()
        if client.set(key, _INSTANCE_ID, nx=True, ex=ttl):
            return True
        holder = client.get(key)
        if holder == _INSTANCE_ID:
            client.expire(key, ttl)
            return True
        return False
    except Exception as exc:
        log.warning("leader lock fallback (single-node): %s — %s", lock_name, exc)
        return True


def release_leader(lock_name: str) -> None:
    if not leader_lock_enabled():
        return
    key = f"matrix:leader:{lock_name}"
    try:
        client = _redis_client()
        if client.get(key) == _INSTANCE_ID:
            client.delete(key)
    except Exception:
        pass


def leader_status() -> dict[str, Any]:
    return {
        "enabled": leader_lock_enabled(),
        "instance_id": _INSTANCE_ID,
        "ttl_sec": lock_ttl_sec(),
    }
