"""投流自动调优 — Redis 可选，离线时使用内存状态。"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from infra.redis_client import redis_client

_local_state: dict[str, str] = {}
_local_logs: list[dict] = []


class AdOptimizer:
    RULES = {
        "high_roi_increase_budget": {
            "condition": lambda m: m["roi"] > 2.0 and m["spend"] < m["budget"] * 0.8,
            "action": "increase_budget",
            "params": {"factor": 1.2},
        },
        "low_roi_pause": {
            "condition": lambda m: m["roi"] < 0.8 and m["spend"] > 50,
            "action": "pause",
            "params": {},
        },
        "high_cpc_reduce_bid": {
            "condition": lambda m: m["cpc"] > m["target_cpc"] * 1.5,
            "action": "reduce_bid",
            "params": {"factor": 0.8},
        },
    }

    async def optimize_loop(self) -> None:
        while True:
            campaigns = await self._fetch_campaign_metrics()
            for campaign in campaigns:
                for rule_name, rule in self.RULES.items():
                    if rule["condition"](campaign):
                        await self._apply_action(campaign, rule)
                        await self._log_optimization(campaign, rule_name)
            await asyncio.sleep(300)

    async def run_once(self) -> dict[str, Any]:
        actions = []
        campaigns = await self._fetch_campaign_metrics()
        for campaign in campaigns:
            for rule_name, rule in self.RULES.items():
                if rule["condition"](campaign):
                    await self._apply_action(campaign, rule)
                    actions.append({"campaign_id": campaign.get("id"), "rule": rule_name, "action": rule["action"]})
        return {"optimized": len(actions), "actions": actions}

    async def _fetch_campaign_metrics(self) -> list[dict]:
        raw = await _redis_get("campaign_metrics")
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        return [
            {
                "id": "demo-1",
                "roi": 2.5,
                "spend": 80,
                "budget": 200,
                "cpc": 1.0,
                "target_cpc": 1.2,
                "bid": 1.0,
            }
        ]

    async def _apply_action(self, campaign: dict, rule: dict) -> None:
        action = rule["action"]
        params = rule["params"]
        cid = str(campaign.get("id"))
        if action == "increase_budget":
            await _redis_set(f"campaign:budget:{cid}", str(campaign["budget"] * params["factor"]))
        elif action == "pause":
            await _redis_set(f"campaign:status:{cid}", "paused")
        elif action == "reduce_bid":
            await _redis_set(f"campaign:bid:{cid}", str(campaign["bid"] * params["factor"]))

    async def _log_optimization(self, campaign: dict, rule_name: str) -> None:
        entry = {"campaign_id": str(campaign.get("id")), "rule": rule_name}
        _local_logs.append(entry)
        try:
            await redis_client.xadd("optimization_log", entry)
        except Exception:
            pass


async def _redis_get(key: str) -> str | None:
    try:
        val = await redis_client.get(key)
        return val
    except Exception:
        return _local_state.get(key)


async def _redis_set(key: str, value: str) -> None:
    _local_state[key] = value
    try:
        await redis_client.set(key, value)
    except Exception:
        pass
