"""Phase15：竞品详情页 views + 飞书审核 callback。"""
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


class VideoDetailTest(unittest.TestCase):
    def test_parse_video_id(self) -> None:
        from services.douyin.video_detail import parse_video_id

        self.assertEqual(parse_video_id("7123456789012345678"), "7123456789012345678")
        self.assertEqual(
            parse_video_id("https://www.douyin.com/video/7123456789012345678"),
            "7123456789012345678",
        )

    def test_enrich_competitors_mock(self) -> None:
        from services.douyin.video_detail import enrich_competitors

        with patch("services.douyin.video_detail.fetch_video_detail") as mock_fetch:
            mock_fetch.return_value = {
                "ok": True,
                "likes": 5000,
                "views": 80000,
                "like_rate": 0.0625,
                "detail_source": "api",
            }
            out = enrich_competitors(
                [{"platform": "douyin", "url": "https://www.douyin.com/video/7123456789012345678", "title": "t"}],
                limit=1,
            )
            self.assertTrue(out[0].get("detail_fetched"))
            self.assertEqual(out[0].get("views"), 80000)
            self.assertTrue(out[0].get("views_from_detail"))


class StrictLikeRateTest(unittest.TestCase):
    def test_strict_requires_real_views(self) -> None:
        from services.perception_engagement import filter_by_like_rate

        items = [{"likes": 600, "title": "无详情"}]
        passed, skipped = filter_by_like_rate(items, min_rate=0.05, strict=True)
        self.assertEqual(len(passed), 0)
        self.assertEqual(skipped[0].get("skip_reason"), "no_real_views")

    def test_strict_passes_detail_views(self) -> None:
        from services.perception_engagement import filter_by_like_rate

        items = [{"likes": 6000, "views": 80000, "views_from_detail": True}]
        passed, skipped = filter_by_like_rate(items, min_rate=0.05, strict=True)
        self.assertEqual(len(passed), 1)
        self.assertGreaterEqual(passed[0]["like_rate"], 0.05)


class FeishuCallbackTest(unittest.TestCase):
    def test_url_verification_challenge(self) -> None:
        from services.feishu_review import handle_review_callback

        out = handle_review_callback({"challenge": "test-challenge-123"})
        self.assertEqual(out.get("challenge"), "test-challenge-123")

    def test_generic_approve_callback(self) -> None:
        from core.storage import init_storage
        from services.feishu_review import handle_review_callback, review_token
        from services.review_queue import submit_for_review

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "cb.db"
            with patch("core.storage.DB_PATH", db), patch("services.feishu_review.send_review_card"):
                init_storage()
                sub = submit_for_review(
                    run_id="run-cb",
                    video_path="D:/v.mp4",
                    script="脚本",
                    notify_feishu=False,
                )
                rid = sub["review_id"]
                tok = review_token(rid)
                out = handle_review_callback({
                    "type": "card.action.trigger",
                    "action": {"value": {"action": "approve", "review_id": rid, "token": tok}},
                })
                self.assertIn("toast", out)
                self.assertTrue(out.get("result", {}).get("ok"))

    def test_build_card_uses_callback_buttons(self) -> None:
        from services.feishu_review import build_review_card

        with patch.dict("os.environ", {"REVIEW_FEISHU_USE_CALLBACK": "1"}):
            card = build_review_card(
                review_id="rev-test",
                run_id="r1",
                title="t",
                video_path="v.mp4",
                script="s",
            )
            actions = card["card"]["elements"][-1]["actions"]
            self.assertIn("value", actions[0])
            self.assertEqual(actions[0]["value"]["action"], "approve")


if __name__ == "__main__":
    unittest.main()
