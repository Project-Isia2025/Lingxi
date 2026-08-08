"""快手开放平台 API 封装。"""
from __future__ import annotations

from typing import Any

import httpx


class KuaishouAPI:
    def __init__(self, access_token: str = "") -> None:
        self.access_token = access_token or "mock-token"
        self.client = httpx.AsyncClient(
            base_url="https://open.kuaishou.com",
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=30.0,
        )
        self._mock_mode = access_token in ("", "xxx", "mock-token")

    async def upload_video(self, video_path: str, title: str, tags: list[str]) -> dict[str, Any]:
        if self._mock_mode:
            return {"video_id": f"mock-ks-{hash(video_path) & 0xFFFF:04x}", "status": "uploaded"}
        resp = await self.client.post(
            "/openapi/photo/upload",
            json={"title": title, "tags": tags},
        )
        resp.raise_for_status()
        return resp.json().get("data", {})

    async def aclose(self) -> None:
        await self.client.aclose()
