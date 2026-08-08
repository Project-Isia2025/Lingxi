"""多平台自动发布。"""
from __future__ import annotations

import os
from typing import Any

from agents.execution.platform_apis.douyin import DouyinAPI
from agents.execution.platform_apis.kuaishou import KuaishouAPI
from agents.execution.platform_apis.weixin import WeixinAPI


class Publisher:
    def __init__(self) -> None:
        dy_token = os.environ.get("DOUYIN_ACCESS_TOKEN", "xxx")
        ks_token = os.environ.get("KUAISHOU_ACCESS_TOKEN", "xxx")
        wx_token = os.environ.get("WEIXIN_ACCESS_TOKEN", "xxx")
        self.platforms = {
            "douyin": DouyinAPI(access_token=dy_token),
            "kuaishou": KuaishouAPI(access_token=ks_token),
            "weixin": WeixinAPI(access_token=wx_token),
        }

    async def publish(self, video_path: str, metadata: dict, platforms: list[str]) -> dict[str, Any]:
        results = {}
        for platform in platforms:
            api = self.platforms.get(platform)
            if api is None:
                results[platform] = {"status": "error", "error": f"unknown platform: {platform}"}
                continue
            try:
                result = await api.upload_video(
                    video_path=video_path,
                    title=metadata["title"],
                    tags=metadata.get("tags", []),
                )
                results[platform] = {**result, "status": "success"}
            except Exception as e:
                results[platform] = {"status": "error", "error": str(e)}
        return results

    async def create_ad(
        self,
        video_id: str,
        budget: float,
        bid: float,
        targeting: dict | None = None,
        platform: str = "douyin",
    ) -> dict:
        api = self.platforms.get(platform)
        if api is None or not hasattr(api, "create_ad"):
            return {"status": "error", "error": "platform does not support ads"}
        return await api.create_ad(video_id, budget, bid, targeting or {})
