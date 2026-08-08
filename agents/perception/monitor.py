"""实时流量波动监控 — Redis 可选。"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from infra.redis_client import redis_client

_prev_campaigns: dict[str, dict] = {}


class TrafficMonitor:
    THRESHOLDS = {
        "traffic_drop_pct": 30,
        "roi_drop_pct": 20,
        "cost_spike_pct": 50,
    }

    async def watch(self) -> None:
        while True:
            campaigns = await self._fetch_active_campaigns()
            for campaign in campaigns:
                change = await self._calc_change(campaign)
                if self._is_abnormal(change):
                    await self._alert(campaign, change)
            await asyncio.sleep(60)

    async def check_all(self) -> dict[str, Any]:
        campaigns = await self._fetch_active_campaigns()
        alerts = []
        for campaign in campaigns:
            change = await self._calc_change(campaign)
            if self._is_abnormal(change):
                alerts.append({"campaign": campaign, "change": change})
        return {"campaigns": len(campaigns), "alerts": alerts, "thresholds": self.THRESHOLDS}

    async def _fetch_active_campaigns(self) -> list[dict]:
        try:
            raw = await redis_client.get("active_campaigns")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return [
            {
                "id": "demo-1",
                "impressions": 1000,
                "spend": 50,
                "roi": 1.5,
                "cpc": 1.1,
                "budget": 200,
            }
        ]

    async def _calc_change(self, campaign: dict) -> dict:
        cid = str(campaign.get("id"))
        prev_key = f"campaign:prev:{cid}"
        prev = _prev_campaigns.get(cid)
        if prev is None:
            try:
                raw = await redis_client.get(prev_key)
                prev = json.loads(raw) if raw else dict(campaign)
            except Exception:
                prev = dict(campaign)

        _prev_campaigns[cid] = dict(campaign)
        try:
            await redis_client.set(prev_key, json.dumps(campaign))
        except Exception:
            pass

        imp_prev = float(prev.get("impressions") or 1)
        imp_now = float(campaign.get("impressions") or 0)
        roi_prev = float(prev.get("roi") or 0)
        roi_now = float(campaign.get("roi") or 0)
        spend_prev = float(prev.get("spend") or 1)
        spend_now = float(campaign.get("spend") or 0)

        return {
            "traffic_change_pct": (imp_now - imp_prev) / imp_prev * 100,
            "roi_change_pct": ((roi_now - roi_prev) / roi_prev * 100) if roi_prev else 0,
            "cost_change_pct": (spend_now - spend_prev) / spend_prev * 100,
        }

    def _is_abnormal(self, change: dict) -> bool:
        if abs(change.get("traffic_change_pct", 0)) >= self.THRESHOLDS["traffic_drop_pct"]:
            return True
        if change.get("roi_change_pct", 0) <= -self.THRESHOLDS["roi_drop_pct"]:
            return True
        if change.get("cost_change_pct", 0) >= self.THRESHOLDS["cost_spike_pct"]:
            return True
        return False

    async def _alert(self, campaign: dict, change: dict) -> None:
        payload = {
            "type": "traffic_anomaly",
            "campaign_id": str(campaign.get("id")),
            "change": json.dumps(change, ensure_ascii=False),
            "timestamp": datetime.now().isoformat(),
        }
        try:
            await redis_client.xadd("alerts", payload)
        except Exception:
            pass
