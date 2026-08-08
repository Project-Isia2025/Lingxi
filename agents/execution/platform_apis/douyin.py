"""抖音开放平台 API 封装。"""
from __future__ import annotations

from typing import Any

import httpx


class DouyinAPI:
    def __init__(self, access_token: str = "") -> None:
        self.access_token = access_token or "mock-token"
        self.client = httpx.AsyncClient(
            base_url="https://open.douyin.com",
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=30.0,
        )
        self._mock_mode = access_token in ("", "xxx", "mock-token")

    async def upload_video(self, video_path: str, title: str, tags: list[str]) -> dict[str, Any]:
        if self._mock_mode:
            return {"video_id": f"mock-dy-{hash(video_path) & 0xFFFF:04x}", "status": "uploaded"}
        resp = await self.client.post(
            "/api/douyin/v1/video/init_upload/",
            json={"title": title, "cover_url": None},
        )
        resp.raise_for_status()
        upload_id = resp.json()["data"]["upload_id"]
        resp = await self.client.post(
            "/api/douyin/v1/video/complete_upload/",
            json={"upload_id": upload_id},
        )
        resp.raise_for_status()
        video_id = resp.json()["data"]["item_id"]
        return {"video_id": video_id, "status": "uploaded"}

    async def create_ad(self, video_id: str, budget: float, bid: float, targeting: dict) -> dict:
        if self._mock_mode:
            return {"ad_id": f"ad-{video_id}", "status": "created"}
        resp = await self.client.post(
            "/api/douyin/v1/ad/create/",
            json={"video_id": video_id, "daily_budget": budget, "bid": bid, "targeting": targeting},
        )
        resp.raise_for_status()
        return resp.json()["data"]

    async def get_ad_stats(self, ad_id: str) -> dict:
        if self._mock_mode:
            return {"ad_id": ad_id, "impressions": 1000, "clicks": 50, "spend": 100}
        resp = await self.client.get("/api/douyin/v1/ad/stats/", params={"ad_id": ad_id})
        resp.raise_for_status()
        return resp.json()["data"]

    async def aclose(self) -> None:
        await self.client.aclose()
