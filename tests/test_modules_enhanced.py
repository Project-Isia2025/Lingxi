"""新增模块单元测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()

from services.ad_optimizer import build_ad_plan
from services.dedup import check_duplicate, dedupe_hash
from services.perception import traffic_volatility
from services.roi import compute_roi
from services.strategy import build_strategy, select_product
from services.video_mix import build_mix_plan
from orchestrator.context import WorkflowContext, WorkflowGoal


class ModuleEnhancementTest(unittest.TestCase):
    def test_traffic_volatility(self) -> None:
        comps = [{"likes": 100, "comments": 10}, {"likes": 9000, "comments": 500}]
        vol = traffic_volatility(comps, [{"title": "热点1"}, {"title": "热点2"}])
        self.assertIn(vol["level"], ("high_opportunity", "moderate", "stable", "unknown"))

    def test_ad_plan(self) -> None:
        plan = build_ad_plan(keyword="护肤", platform="douyin", strategy={}, perception={"traffic_trend": {"trend": "cold_start"}}, budget_limit=100)
        self.assertIn("daily_budget_cny", plan)
        self.assertEqual(len(plan.get("creative_tests") or []), 3)

    def test_mix_plan(self) -> None:
        plan = build_mix_plan(script="钩子。痛点。方案。证据。行动。", keyword="测试")
        self.assertTrue(plan.get("timeline"))
        self.assertGreater(plan.get("total_duration_sec", 0), 0)

    def test_dedup(self) -> None:
        h = dedupe_hash("测试脚本内容")
        self.assertEqual(len(h), 16)
        dup = check_duplicate("全新未重复的内容ABC123")
        self.assertFalse(dup.get("duplicate"))

    def test_strategy_enhanced(self) -> None:
        s = build_strategy(
            keyword="护肤",
            platform="douyin",
            perception={"competitors": [{"title": "爆款", "likes": 6000}], "traffic_trend": {"trend": "rising"}},
            memory={"geo": {}, "top_kb_items": []},
            budget_limit=200,
            video_provider="template",
        )
        self.assertIn("product_selection", s)
        self.assertIn("ad_plan", s)
        self.assertIn("pricing_tiers", s)

    def test_roi_compute(self) -> None:
        ctx = WorkflowContext(
            goal=WorkflowGoal(keyword="护肤"),
            perception={"competitors": [{}], "traffic_trend": {"trend": "stable"}, "traffic_volatility": {"level": "moderate"}},
            memory={"sop_entries": [{}]},
            strategy={"product_selection": {}, "ad_plan": {}, "video_cost_plan": {}},
            content={"script": "x" * 50, "risk_check": {"passed": True}, "channel_contents": {}, "variants": [{}]},
            execution={"ad_optimize_plan": {}, "auto_started": True},
        )
        roi = compute_roi(ctx)
        self.assertGreater(roi["roi_score"], 0)
        self.assertIn(roi["grade"], ("A", "B", "C", "D"))

    def test_select_product(self) -> None:
        p = select_product("护肤", {"competitors": [{"likes": 8000, "title": "爆款"}], "viral_rank": []}, {})
        self.assertEqual(p["product_type"], "爆款对标款")


if __name__ == "__main__":
    unittest.main()
