"""Phase5：调价规则 UI、ASR 转写、多账号发布调度。"""
from __future__ import annotations

import json
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


class AdBidConfigTest(unittest.TestCase):
    def test_load_save_rules(self) -> None:
        from services.ad_bid_config import DEFAULT_RULES, load_bid_rules, save_bid_rules

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "rules.json"
            import os

            os.environ["AD_BID_RULES_PATH"] = str(p)
            saved = save_bid_rules({**DEFAULT_RULES, "ctr_good": 0.025})
            self.assertEqual(saved["ctr_good"], 0.025)
            loaded = load_bid_rules()
            self.assertEqual(loaded["ctr_good"], 0.025)

    def test_rule_toggle_disables_action(self) -> None:
        from services.ad_bid_config import save_bid_rules
        from services.ad_bid_engine import evaluate_bid_rules

        with tempfile.TemporaryDirectory() as td:
            import os

            p = Path(td) / "rules.json"
            os.environ["AD_BID_RULES_PATH"] = str(p)
            save_bid_rules({
                "rules": [
                    {"id": "low_ctr", "label": "CTR 过低", "enabled": False, "priority": 3},
                    {"id": "high_cpc", "enabled": True, "priority": 3},
                    {"id": "low_roi", "enabled": True, "priority": 2},
                    {"id": "good_roi_ctr", "enabled": True, "priority": 2},
                    {"id": "good_ctr", "enabled": True, "priority": 1},
                ]
            })
            d = evaluate_bid_rules(
                metrics={"impressions": 2000, "clicks": 5, "cost_cny": 80, "ctr": 0.002},
                ad_roi_score=0.3,
                daily_budget_cny=100,
            )
            self.assertNotEqual(d.get("rule_id"), "low_ctr")


class AsrModuleTest(unittest.TestCase):
    @patch("requests.post")
    def test_transcribe_audio_api(self, mock_post) -> None:
        import os

        os.environ["ASR_API_BASE"] = "https://api.example.com/v1"
        os.environ["ASR_API_KEY"] = "sk-test"
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"text": "这是转写文本"}
        mock_post.return_value.raise_for_status = lambda: None

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"RIFF")
            path = f.name
        try:
            from services.asr import transcribe_audio_file

            out = transcribe_audio_file(path)
            self.assertTrue(out.get("ok"))
            self.assertIn("转写", out.get("text", ""))
        finally:
            Path(path).unlink(missing_ok=True)

    def test_collect_asr_context(self) -> None:
        from services.content import collect_ocr_context

        perception = {"competitors": [{"title": "视频笔记", "asr_text": "口播里的核心卖点一句话"}]}
        ctx = collect_ocr_context(perception)
        self.assertIn("ASR", ctx)
        self.assertIn("卖点", ctx)


class PublishSchedulerTest(unittest.TestCase):
    def test_schedule_and_queue(self) -> None:
        from core.storage import init_storage, list_publish_queue, upsert_publish_account

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "test.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()

                upsert_publish_account(
                    platform="douyin",
                    account_id="acc1",
                    label="测试号",
                    storage_state="",
                    daily_limit=5,
                )
                from services.publish.scheduler import schedule_publish, run_publish_queue

                vid = Path(td) / "v.mp4"
                vid.write_bytes(b"x" * 1000)
                with patch("services.publish.scheduler.sync_accounts_to_db", return_value=0):
                    out = schedule_publish(
                        platform="douyin",
                        video_path=str(vid),
                        script="测试文案",
                        account_id="acc1",
                    )
                self.assertTrue(out.get("ok"))
                self.assertIn("job_id", out)

                queued = list_publish_queue(status="queued", limit=5)
                self.assertGreaterEqual(len(queued), 1)

                with patch("services.publish.scheduler.publish_to_platform") as mock_pub:
                    mock_pub.return_value = {"success": True, "post_url": "https://example.com/p/1"}
                    run_out = run_publish_queue(limit=5, dry_run=False)
                    self.assertTrue(run_out.get("ok"))
                    self.assertGreaterEqual(run_out.get("success", 0), 1)


class StoragePublishTest(unittest.TestCase):
    def test_pick_publish_account(self) -> None:
        from core.storage import init_storage, pick_publish_account, upsert_publish_account

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "t.db"
            with patch("core.storage.DB_PATH", db):
                init_storage()
                upsert_publish_account(platform="douyin", account_id="a1", daily_limit=3)
                upsert_publish_account(platform="douyin", account_id="a2", daily_limit=3)
                picked = pick_publish_account("douyin")
                self.assertIn(picked, ("a1", "a2"))


class NoteDetailAsrTest(unittest.TestCase):
    @patch("services.asr.transcribe_url")
    def test_apply_note_asr(self, mock_asr) -> None:
        mock_asr.return_value = {"ok": True, "text": "视频口播内容"}
        from services.xhs.note_detail import _apply_note_asr

        data = {"body": "短", "video_urls": ["https://cdn.example.com/v.mp4"]}
        out = _apply_note_asr(data)
        self.assertTrue(out.get("ok"))
        self.assertIn("口播", data.get("asr_text", ""))


if __name__ == "__main__":
    unittest.main()
