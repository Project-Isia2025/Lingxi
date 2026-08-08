"""Phase4：调价引擎、OCR 注入、Windows 脚本辅助测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


class AdBidEngineTest(unittest.TestCase):
    def test_increase_on_good_roi(self) -> None:
        from services.ad_bid_engine import evaluate_bid_rules

        d = evaluate_bid_rules(
            metrics={"impressions": 2000, "clicks": 50, "cost_cny": 80, "ctr": 0.025},
            ad_roi_score=0.7,
            daily_budget_cny=100,
        )
        self.assertEqual(d["action"], "increase_budget")

    def test_decrease_on_low_ctr(self) -> None:
        from services.ad_bid_engine import evaluate_bid_rules

        d = evaluate_bid_rules(
            metrics={"impressions": 2000, "clicks": 5, "cost_cny": 80, "ctr": 0.002},
            ad_roi_score=0.3,
            daily_budget_cny=100,
        )
        self.assertEqual(d["action"], "decrease_budget")

    @patch("services.ad_bid_engine.apply_bid_decision")
    @patch("services.ad_bid_engine.get_ad_campaign_by_run")
    def test_run_auto_bid(self, mock_get, mock_apply) -> None:
        mock_get.return_value = {
            "run_id": "r1",
            "campaign_id": "dry_1",
            "daily_budget": 100,
            "dry_run": True,
            "last_report": {"metrics": {"impressions": 2000, "clicks": 50, "cost_cny": 80, "ctr": 0.025}, "ad_roi_score": 0.7},
        }
        mock_apply.return_value = {"ok": True, "applied": True}
        from services.ad_bid_engine import run_auto_bid_for_run

        out = run_auto_bid_for_run("r1", apply=True)
        self.assertTrue(out.get("ok"))


class OcrInjectTest(unittest.TestCase):
    def test_collect_ocr_context(self) -> None:
        from services.content import collect_ocr_context

        perception = {
            "competitors": [{"title": "笔记", "ocr_text": "图片里识别到的卖点文案"}],
            "breakdowns": [{"platform": "xiaohongshu", "original_transcript": "x" * 100}],
        }
        ctx = collect_ocr_context(perception)
        self.assertIn("OCR", ctx)
        self.assertIn("卖点", ctx)


class BootstrapEnvTest(unittest.TestCase):
    def test_load_local_env_no_crash(self) -> None:
        bootstrap.load_local_env()
        self.assertTrue(bootstrap.project_root().joinpath("config", "local.env.example").is_file())


if __name__ == "__main__":
    unittest.main()
