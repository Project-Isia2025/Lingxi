"""阿里云 FC HTTP 触发器 → FastAPI ASGI 适配。"""
from __future__ import annotations

import base64
import json
import sys
from io import BytesIO
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


def _fc_event_to_scope(event: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    ctx = event.get("requestContext") or {}
    http = ctx.get("http") or {}
    method = (http.get("method") or event.get("httpMethod") or "GET").upper()
    path = event.get("rawPath") or event.get("path") or "/"
    query = event.get("rawQueryString") or event.get("queryString") or ""
    if query and "?" not in path:
        path = f"{path}?{query}"

    headers_in = event.get("headers") or {}
    headers: list[tuple[bytes, bytes]] = []
    for key, val in headers_in.items():
        headers.append((key.lower().encode("latin-1", "ignore"), str(val).encode("latin-1", "ignore")))

    body_raw = event.get("body") or ""
    if event.get("isBase64Encoded") and body_raw:
        body = base64.b64decode(body_raw)
    elif isinstance(body_raw, str):
        body = body_raw.encode("utf-8")
    else:
        body = b""

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path.split("?", 1)[0],
        "raw_path": path.encode("utf-8"),
        "query_string": query.encode("utf-8"),
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 0),
        "server": ("fc.aliyun.com", 443),
    }
    return scope, body


class _ResponseCollector:
    def __init__(self) -> None:
        self.status = 200
        self.headers: list[tuple[bytes, bytes]] = []
        self.body = BytesIO()

    async def __call__(self, message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            self.status = int(message.get("status") or 200)
            self.headers = list(message.get("headers") or [])
        elif message["type"] == "http.response.body":
            self.body.write(message.get("body") or b"")


async def _invoke_app(event: dict[str, Any]) -> dict[str, Any]:
    from api.routes import app

    scope, body = _fc_event_to_scope(event)
    collector = _ResponseCollector()
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    await app(scope, receive, collector.__call__)

    headers_out = {k.decode("latin-1", "ignore"): v.decode("latin-1", "ignore") for k, v in collector.headers}
    payload = collector.body.getvalue()
    is_binary = "application/octet-stream" in headers_out.get("content-type", "")
    return {
        "statusCode": collector.status,
        "headers": headers_out,
        "body": base64.b64encode(payload).decode("ascii") if is_binary else payload.decode("utf-8", "replace"),
        "isBase64Encoded": is_binary,
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """阿里云 FC 入口：包装 Campaign API（api/routes.py）。"""
    import asyncio

    if isinstance(event, (str, bytes)):
        try:
            event = json.loads(event)
        except Exception:
            event = {"rawPath": "/", "requestContext": {"http": {"method": "GET"}}}
    if not isinstance(event, dict):
        event = {}

    try:
        return asyncio.run(_invoke_app(event))
    except Exception as exc:
        return {
            "statusCode": 500,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"ok": False, "error": "fc_handler_failed", "detail": str(exc)[:300]}),
            "isBase64Encoded": False,
        }
