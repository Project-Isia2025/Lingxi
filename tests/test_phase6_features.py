"""Phase6：发布队列 Worker、ASR 记忆入库。"""
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


class AsrMemoryTest(unittest.TestCase):
    def test_ingest_asr_transcript(self) -> None:
        from core.storage import init_storage, kb_search
        from services.asr_memory import ingest_asr_transcript

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mem.db"
            with patch("core.db.DB_PATH", db), patch("core.storage.DB_PATH", db):
                init_storage()
                out = ingest_asr_transcript(
                    text="这是竞品视频口播的核心卖点描述",
                    title="测试笔记",
                    note_id="abc123",
                    keyword="护肤",
                )
                self.assertTrue(out.get("ok"))
                hits = kb_search(query="护肤", library="hotspot", limit=5)
                self.assertTrue(any("ASR" in str(h.get("title") or "") for h in hits))

    def test_ingest_disabled(self) -> None:
        import os

        os.environ["ASR_MEMORY_ENABLED"] = "0"
        from services.asr_memory import ingest_asr_transcript

        out = ingest_asr_transcript(text="hello")
        self.assertFalse(out.get("ok"))
        os.environ["ASR_MEMORY_ENABLED"] = "1"


class PublishWorkerTest(unittest.TestCase):
    def test_worker_status(self) -> None:
        from services.publish_worker import get_worker_status, worker_enabled

        st = get_worker_status()
        self.assertTrue(st.get("ok"))
        self.assertIn("pending_queued", st)
        self.assertIsInstance(worker_enabled(), bool)

    @patch("services.workers.publish_worker.run_publish_queue")
    def test_run_queue_once(self, mock_run) -> None:
        mock_run.return_value = {"ok": True, "processed": 2, "success": 2, "results": []}
        from services.publish_worker import run_queue_once

        out = run_queue_once(limit=3)
        self.assertTrue(out.get("ok"))
        mock_run.assert_called_once_with(limit=3, dry_run=False)


if __name__ == "__main__":
    unittest.main()
