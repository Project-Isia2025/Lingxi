"""小红书爬虫单元测试。"""
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

from services.xhs import common as xc


class XhsCommonTest(unittest.TestCase):
    def test_parse_count(self) -> None:
        self.assertEqual(xc.parse_count_text("2.3万"), 23000)

    def test_build_search_url(self) -> None:
        url = xc.build_search_url("护肤")
        self.assertIn("xiaohongshu.com/search_result", url)


class XhsSearchTest(unittest.TestCase):
    @patch("services.xhs.search._fetch_raw")
    def test_search_success(self, mock_fetch) -> None:
        mock_fetch.return_value = (
            [
                {
                    "note_id": "abc123def456789012345678",
                    "url": "https://www.xiaohongshu.com/explore/abc123def456789012345678",
                    "title": "测试笔记",
                    "likes_text": "3.2万",
                }
            ],
            False,
        )
        with patch("services.xhs.search.xc.resolve_storage_state", return_value="/fake.json"):
            from services.xhs.search import search_xhs

            out = search_xhs("护肤", limit=5)
        self.assertTrue(out.get("ok"))
        self.assertEqual(out["items"][0]["likes"], 32000)


class PerceptionXhsIntegrationTest(unittest.TestCase):
    @patch("services.xhs.search.search_xhs")
    def test_perception_uses_xhs_crawler(self, mock_search) -> None:
        mock_search.return_value = {
            "ok": True,
            "items": [{"title": "小红书真实", "likes": 500, "url": "https://www.xiaohongshu.com/explore/x", "platform": "xiaohongshu"}],
        }
        from services.perception import perceive_market

        out = perceive_market(keyword="护肤", platform="xhs", reference_urls=[])
        self.assertEqual(out["crawl_meta"]["source"], "live_crawler")
        self.assertEqual(out["competitors"][0]["title"], "小红书真实")


if __name__ == "__main__":
    unittest.main()
