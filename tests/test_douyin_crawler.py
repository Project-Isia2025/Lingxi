"""抖音爬虫单元测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()

from services.douyin import common as dc


class DouyinCommonTest(unittest.TestCase):
    def test_parse_count_wan(self) -> None:
        self.assertEqual(dc.parse_count_text("1.2万"), 12000)
        self.assertEqual(dc.parse_count_text("3.5w"), 35000)

    def test_build_search_url(self) -> None:
        url = dc.build_search_url("敏感肌")
        self.assertIn("douyin.com/search", url)
        self.assertIn("%", url)


class DouyinSearchTest(unittest.TestCase):
    @patch("services.douyin.search._fetch_raw")
    def test_search_success(self, mock_fetch) -> None:
        mock_fetch.return_value = (
            [
                {
                    "video_id": "7123456789012345678",
                    "url": "https://www.douyin.com/video/7123456789012345678",
                    "title": "测试视频",
                    "likes_text": "1.2万",
                    "followers_text": "10万",
                }
            ],
            False,
        )
        with patch("services.douyin.search.dc.resolve_storage_state", return_value="/fake.json"):
            from services.douyin.search import search_douyin

            out = search_douyin("护肤", limit=5)
        self.assertTrue(out.get("ok"))
        self.assertEqual(len(out.get("items") or []), 1)
        self.assertEqual(out["items"][0]["likes"], 12000)

    def test_search_missing_cookie(self) -> None:
        with patch("services.douyin.search.dc.resolve_storage_state", return_value=""), patch(
            "services.douyin.search.dc.resolve_cookie_file", return_value=""
        ):
            from services.douyin.search import search_douyin

            out = search_douyin("护肤")
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "douyin_cookie_missing")


class PerceptionDouyinIntegrationTest(unittest.TestCase):
    @patch("services.douyin.search.search_douyin")
    def test_perception_uses_crawler(self, mock_search) -> None:
        mock_search.return_value = {
            "ok": True,
            "items": [{"title": "真实抓取", "likes": 999, "url": "https://www.douyin.com/video/1", "platform": "douyin"}],
        }
        from services.perception import perceive_market

        out = perceive_market(keyword="护肤", platform="douyin", reference_urls=[])
        self.assertEqual(out["crawl_meta"]["source"], "live_crawler")
        self.assertEqual(out["competitors"][0]["title"], "真实抓取")


if __name__ == "__main__":
    unittest.main()
