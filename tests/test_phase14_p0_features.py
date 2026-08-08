"""Phase14 P0：感知调度、库存日指令、飞书审核队列。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


class PerceptionEngagementTest(unittest.TestCase):
    def test_like_rate_filter(self) -> None:
        from services.perception_engagement import filter_by_like_rate

        items = [
            {"title": "高互动", "likes": 600, "views": 10000},
            {"title": "低互动", "likes": 100, "views": 10000},
        ]
        passed, skipped = filter_by_like_rate(items, min_rate=0.05)
        self.assertEqual(len(passed), 1)
        self.assertEqual(len(skipped), 1)
        self.assertAlmostEqual(passed[0]["like_rate"], 0.06)


class HotlistTest(unittest.TestCase):
    def test_curated_hotlist(self) -> None:
        from services.douyin.hotlist import fetch_douyin_hotlist

        with patch("services.douyin.hotlist.dc.douyin_enabled", return_value=False):
            out = fetch_douyin_hotlist(limit=5)
        self.assertTrue(out.get("ok"))
        self.assertGreaterEqual(out.get("count", 0), 1)


class PerceptionScanTest(unittest.TestCase):
    def test_run_scan(self) -> None:
        from services.perception import run_perception_scan

        out = run_perception_scan(keyword="A面膜", run_id="scan-test")
        self.assertTrue(out.get("ok"))
        self.assertIn("competitors", out)
        self.assertIn("hotlist", out)


class InventoryDirectiveTest(unittest.TestCase):
    def test_primary_product_stock(self) -> None:
        from services.inventory import get_primary_product

        inv = get_primary_product()
        self.assertTrue(inv.get("ok"))
        self.assertEqual(inv["product"]["name"], "A款面膜")
        self.assertGreaterEqual(int(inv["product"]["stock"]), 2000)

    def test_daily_directive_three_slices(self) -> None:
        from services.daily_directive import build_daily_directive

        out = build_daily_directive(
            keyword="A面膜",
            perception={"hotlist": [{"title": "春季护肤"}], "hotspots": []},
            memory={},
        )
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("slice_count"), 3)
        self.assertEqual(out["slices"][0]["duration_sec"], 15)
        self.assertIn("痛点+解决方案", out.get("instruction", ""))
        self.assertIn("2000", out.get("instruction", ""))

    def test_strategy_has_daily_directive(self) -> None:
        from services.strategy import build_strategy

        strat = build_strategy(
            keyword="A面膜",
            platform="douyin",
            perception={"competitors": [{"likes": 6000, "title": "爆款"}], "traffic_trend": {}, "hotlist": []},
            memory={"geo": {}},
            budget_limit=5.0,
            video_provider="template",
        )
        daily = strat.get("daily_directive") or {}
        self.assertEqual(len(strat.get("variants") or []), 3)
        self.assertEqual(daily.get("slice_count"), 3)


class ReviewQueueTest(unittest.TestCase):
    @patch("services.feishu_review.send_review_card")
    def test_submit_approve(self, mock_card) -> None:
        mock_card.return_value = {"ok": True}
        from core.storage import init_storage
        from services.feishu_review import review_token
        from services.review_queue import approve_review, submit_for_review

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "r.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()
                sub = submit_for_review(
                    run_id="run-r1",
                    video_path="D:/v.mp4",
                    script="测试脚本" * 20,
                    title="测试",
                    notify_feishu=False,
                )
                self.assertTrue(sub.get("ok"))
                rid = sub["review_id"]
                out = approve_review(review_id=rid, token=review_token(rid))
                self.assertTrue(out.get("ok"))
                self.assertEqual(out.get("status"), "approved")

    @patch("services.feishu_review.send_review_card")
    def test_reject_learns(self, mock_card) -> None:
        mock_card.return_value = {"ok": True}
        from core.storage import init_storage, kb_search
        from services.feishu_review import review_token
        from services.review_queue import reject_review, submit_for_review

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "r2.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()
                sub = submit_for_review(
                    run_id="run-r2",
                    video_path="D:/v.mp4",
                    script="测试",
                    notify_feishu=False,
                )
                rid = sub["review_id"]
                out = reject_review(review_id=rid, reason="开场不够痛，需加强痛点", token=review_token(rid))
                self.assertTrue(out.get("ok"))
                hits = kb_search(query="打回", library="sop", limit=5)
                self.assertTrue(any("打回" in str(h.get("title") or "") for h in hits))


class ExecutionReviewTest(unittest.TestCase):
    @patch("services.feishu_review.send_review_card")
    @patch("services.execution.deploy_ad_plan")
    @patch("services.execution.quality_gate")
    def test_build_execution_submits_review(self, mock_qg, mock_deploy, mock_card) -> None:
        mock_qg.return_value = {"passed": True, "warnings": []}
        mock_deploy.return_value = None
        mock_card.return_value = {"ok": True}

        from orchestrator.context import WorkflowGoal
        from services.execution import build_execution

        goal = WorkflowGoal(keyword="A面膜", video_path="D:/v.mp4")
        out = build_execution(
            run_id="run-ex-review",
            goal=goal,
            strategy={"target_platform": "douyin", "primary_keyword": "A面膜", "channels": ["short_video"]},
            content={"script": "测试口播文案" * 10, "risk_check": {"passed": True}},
            exec_url="",
        )
        self.assertIsNotNone(out.get("review"))
        self.assertTrue(out["review"].get("ok"))
        self.assertFalse(out.get("published"))


class InsightsIngestTest(unittest.TestCase):
    def test_golden_hook_and_bgm(self) -> None:
        from core.storage import init_storage
        from services.perception_insights import extract_golden_hook, ingest_competitor_insights

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "i.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()
                hook = extract_golden_hook(title="为什么90%的人护肤都错了")
                self.assertTrue(hook)
                out = ingest_competitor_insights(
                    competitors=[{"title": "爆款护肤", "snippet": "你知道吗？90%的人第一步就错了。后面内容..."}],
                    keyword="护肤",
                )
                self.assertTrue(out.get("ok"))
                self.assertGreaterEqual(out.get("hooks_ingested", 0), 1)


if __name__ == "__main__":
    unittest.main()
