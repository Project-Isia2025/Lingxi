"""轮询、OCR、多音色 A/B 测试。"""
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


class AdSchedulerTest(unittest.TestCase):
    @patch("services.workers.ad_scheduler.list_ad_campaigns")
    @patch("services.workers.ad_scheduler.sync_ad_report_for_run")
    def test_poll_all(self, mock_sync, mock_list) -> None:
        mock_list.return_value = [{"run_id": "r1"}, {"run_id": "r2"}]
        mock_sync.return_value = {"ok": True, "ad_roi_score": 0.5}
        from services.ad_scheduler import poll_all_campaigns

        out = poll_all_campaigns()
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("success"), 2)

    def test_poll_status(self) -> None:
        from services.ad_scheduler import get_poll_status

        st = get_poll_status()
        self.assertIn("enabled", st)


class OcrTest(unittest.TestCase):
    @patch("services.ocr._pytesseract_available", return_value=False)
    @patch("services.ocr._ocr_with_llm_vision", return_value="图片中的文字")
    def test_ocr_bytes_llm(self, mock_llm, _tess) -> None:
        from services.ocr import ocr_image_bytes

        out = ocr_image_bytes(b"\xff\xd8\xff fake jpeg")
        self.assertTrue(out.get("ok"))
        self.assertIn("文字", out.get("text", ""))

    @patch("services.ocr.download_image")
    @patch("services.ocr.ocr_image_bytes")
    def test_ocr_images_merge(self, mock_ocr, mock_dl) -> None:
        mock_dl.return_value = b"img"
        mock_ocr.return_value = {"ok": True, "text": "第一句"}
        from services.ocr import ocr_images

        out = ocr_images(["https://example.com/a.jpg", "https://example.com/b.jpg"], limit=2)
        self.assertTrue(out.get("ok"))


class TtsAbTest(unittest.TestCase):
    @patch("services.tts.synthesize_speech")
    def test_synthesize_ab_variants(self, mock_syn) -> None:
        mock_syn.side_effect = [
            {"ok": True, "output_path": "/a.mp3", "provider": "edge_tts"},
            {"ok": True, "output_path": "/b.mp3", "provider": "edge_tts"},
        ]
        from services.tts import synthesize_ab_variants

        out = synthesize_ab_variants("测试口播", run_id="abtest01", voices=["v1", "v2"])
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("count"), 2)
        self.assertEqual(out.get("recommended"), "A")


class NoteOcrIntegrationTest(unittest.TestCase):
    @patch("services.xhs.note_detail._fetch_note_page")
    @patch("services.ocr.ocr_images")
    def test_fetch_with_ocr(self, mock_ocr, mock_page) -> None:
        mock_page.return_value = (
            {
                "note_id": "abc123def456789012345678",
                "title": "标题",
                "body": "短",
                "tags": [],
                "likes": 100,
                "image_urls": ["https://example.com/1.jpg"],
            },
            False,
        )
        mock_ocr.return_value = {"ok": True, "merged_text": "OCR识别正文内容", "image_count": 1, "success_count": 1}
        with patch("services.xhs.note_detail.xc.resolve_storage_state", return_value="/fake.json"):
            from services.xhs.note_detail import fetch_note_detail

            out = fetch_note_detail("abc123def456789012345678")
        self.assertTrue(out.get("ok"))
        self.assertIn("OCR", out.get("ocr_text", ""))


if __name__ == "__main__":
    unittest.main()
