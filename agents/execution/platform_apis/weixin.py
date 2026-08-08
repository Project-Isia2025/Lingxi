"""微信视频号 API 封装。"""
from __future__ import annotations

from typing import Any

import httpx


class WeixinAPI:
    def __init__(self, access_token: str = "") -> None:
        self.access_token = access_token or "mock-token"
        self.client = httpx.AsyncClient(
            base_url="https://api.weixin.qq.com",
            timeout=30.0,
        )
        self._mock_mode = access_token in ("", "xxx", "mock-token")

    async def upload_video(self, video_path: str, title: str, tags: list[str]) -> dict[str, Any]:
        if self._mock_mode:
            return {"video_id": f"mock-wx-{hash(video_path) & 0xFFFF:04x}", "status": "uploaded"}
        resp = await self.client.post(
            "/channels/ec/video/upload",
            params={"access_token": self.access_token},
            json={"title": title, "tags": tags},
        )
        resp.raise_for_status()
        return resp.json()

    async def aclose(self) -> None:
        await self.client.aclose()
