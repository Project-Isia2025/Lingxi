"""Phase7：发布 ROI 回写、队列重试、感知 Feed。"""
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


class PublishFeedbackTest(unittest.TestCase):
    def test_compute_publish_roi(self) -> None:
        from services.publish_feedback import compute_publish_roi_score

        s = compute_publish_roi_score(
            platform="douyin",
            post_url="https://www.douyin.com/video/1",
            script="x" * 200,
        )
        self.assertGreaterEqual(s, 0.7)

    def test_apply_publish_success(self) -> None:
        from core.storage import init_storage, metrics_summary
        from services.publish_feedback import apply_publish_success_feedback

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "fb.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()
                out = apply_publish_success_feedback(
                    platform="douyin",
                    script="测试发布文案内容",
                    post_url="https://example.com/p/1",
                    keyword="护肤",
                )
                self.assertTrue(out.get("ok"))
                self.assertGreater(float(out.get("publish_roi_score") or 0), 0)


class PublishRetryTest(unittest.TestCase):
    def test_retriable_error(self) -> None:
        from services.publish_retry import is_retriable_error

        self.assertFalse(is_retriable_error("storage_state_missing"))
        self.assertTrue(is_retriable_error("timeout"))

    @patch("services.publish_retry.apply_publish_failure_feedback")
    @patch("services.publish_retry.requeue_publish_job")
    @patch("services.publish_retry.get_publish_queue_job")
    def test_handle_failure_requeue(self, mock_get, mock_requeue, mock_fail) -> None:
        mock_get.return_value = {"payload": {"retry_count": 0}}
        from services.publish_retry import handle_publish_failure

        job = {"job_id": "j1", "platform": "douyin", "run_id": "r1"}
        out = handle_publish_failure(job, {"success": False, "error": "timeout"})
        self.assertEqual(out.get("status"), "queued")
        mock_requeue.assert_called_once()

    @patch("services.publish_retry.apply_publish_failure_feedback")
    @patch("services.publish_retry.update_publish_queue_status")
    @patch("services.publish_retry.get_publish_queue_job")
    def test_handle_non_retriable(self, mock_get, mock_update, mock_fail) -> None:
        mock_get.return_value = {"payload": {}}
        from services.publish_retry import handle_publish_failure

        out = handle_publish_failure(
            {"job_id": "j2", "platform": "douyin"},
            {"success": False, "error": "publish_disabled"},
        )
        self.assertEqual(out.get("status"), "failed")
        mock_update.assert_called_once()


class PerceptionFeedTest(unittest.TestCase):
    def test_kb_list_recent(self) -> None:
        from core.storage import init_storage, kb_list_recent, kb_upsert

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "k.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()
                kb_upsert(library="hotspot", title="ASR·测试", body="口播文本", tags="asr,test", platform="xhs")
                rows = kb_list_recent(tag_contains="asr", limit=5)
                self.assertGreaterEqual(len(rows), 1)

    def test_ingest_ocr(self) -> None:
        from core.storage import init_storage, kb_list_recent
        from services.asr_memory import ingest_ocr_text

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "o.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()
                out = ingest_ocr_text(text="图片里的文字内容", title="笔记OCR")
                self.assertTrue(out.get("ok"))
                self.assertGreaterEqual(len(kb_list_recent(tag_contains="ocr", limit=5)), 1)


if __name__ == "__main__":
    unittest.main()
