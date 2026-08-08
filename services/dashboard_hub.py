"""Dashboard WebSocket 广播 Hub（Feed + Analytics + Runtime）。"""
from __future__ import annotations

import asyncio
import logging
import threading

from fastapi import WebSocket

from services.dashboard_feed import build_perception_feed
from services.dashboard_metrics import build_metrics_chart

log = logging.getLogger(__name__)

_feed_connections: list[WebSocket] = []
_analytics_connections: list[WebSocket] = []
_runtime_connections: list[tuple[WebSocket, str, str]] = []
_lock = threading.Lock()


async def connect_feed(ws: WebSocket) -> None:
    await ws.accept()
    with _lock:
        _feed_connections.append(ws)
    await ws.send_json({**build_perception_feed(), "event": "snapshot", "channel": "feed"})


async def connect_analytics(ws: WebSocket) -> None:
    await ws.accept()
    with _lock:
        _analytics_connections.append(ws)
    await ws.send_json({**build_metrics_chart(), "event": "snapshot", "channel": "analytics"})


async def connect_runtime(ws: WebSocket, *, org_id: str = "", platform: str = "douyin") -> None:
    from services.runtime_dashboard import build_runtime_dashboard

    await ws.accept()
    oid = (org_id or "").strip()
    plat = (platform or "douyin").strip().lower() or "douyin"
    with _lock:
        _runtime_connections.append((ws, oid, plat))
    await ws.send_json({
        **build_runtime_dashboard(platform=plat, org_id=oid),
        "event": "snapshot",
        "channel": "runtime",
    })


async def disconnect_feed(ws: WebSocket) -> None:
    with _lock:
        if ws in _feed_connections:
            _feed_connections.remove(ws)


async def disconnect_analytics(ws: WebSocket) -> None:
    with _lock:
        if ws in _analytics_connections:
            _analytics_connections.remove(ws)


async def disconnect_runtime(ws: WebSocket) -> None:
    with _lock:
        _runtime_connections[:] = [(w, o, p) for w, o, p in _runtime_connections if w is not ws]


async def connect(ws: WebSocket) -> None:
    await connect_feed(ws)


async def disconnect(ws: WebSocket) -> None:
    await disconnect_feed(ws)


async def broadcast_feed(*, reason: str = "") -> None:
    if not _feed_connections:
        return
    payload = {**build_perception_feed(), "event": "update", "reason": reason, "channel": "feed"}
    await _send_all(_feed_connections, payload)


async def broadcast_chart(*, reason: str = "", days: int = 14) -> None:
    if not _analytics_connections:
        return
    payload = {**build_metrics_chart(days=days), "event": "update", "reason": reason, "channel": "analytics"}
    await _send_all(_analytics_connections, payload)


async def broadcast_runtime(*, reason: str = "") -> None:
    from services.runtime_dashboard import build_runtime_dashboard

    with _lock:
        conns = list(_runtime_connections)
    if not conns:
        return
    dead: list[WebSocket] = []
    for ws, oid, plat in conns:
        try:
            await ws.send_json({
                **build_runtime_dashboard(platform=plat, org_id=oid),
                "event": "update",
                "reason": reason,
                "channel": "runtime",
            })
        except Exception:
            dead.append(ws)
    if dead:
        with _lock:
            _runtime_connections[:] = [(w, o, p) for w, o, p in _runtime_connections if w not in dead]


async def _send_all(targets: list[WebSocket], payload: dict) -> None:
    dead: list[WebSocket] = []
    with _lock:
        conns = list(targets)
    for ws in conns:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    if dead:
        with _lock:
            for ws in dead:
                if ws in _feed_connections:
                    _feed_connections.remove(ws)
                if ws in _analytics_connections:
                    _analytics_connections.remove(ws)


def notify_dashboard_update(reason: str = "") -> None:
    """从同步代码触发 Feed / 图表 / 运维面板刷新。"""
    need_feed = connection_count() > 0
    need_chart = analytics_connection_count() > 0
    need_runtime = runtime_connection_count() > 0
    if not need_feed and not need_chart and not need_runtime:
        return

    async def _all() -> None:
        if need_feed:
            await broadcast_feed(reason=reason)
        if need_chart:
            await broadcast_chart(reason=reason)
        if need_runtime:
            await broadcast_runtime(reason=reason)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_all())
        return
    except RuntimeError:
        pass

    def _runner() -> None:
        try:
            asyncio.run(_all())
        except Exception:
            log.debug("dashboard broadcast skipped", exc_info=True)

    threading.Thread(target=_runner, daemon=True, name="dashboard-broadcast").start()


def connection_count() -> int:
    with _lock:
        return len(_feed_connections)


def analytics_connection_count() -> int:
    with _lock:
        return len(_analytics_connections)


def runtime_connection_count() -> int:
    with _lock:
        return len(_runtime_connections)
