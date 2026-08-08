"""Phase21：切片审核通过后矩阵发布 + Playwright Docker。"""
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


class SlicePublishTest(unittest.TestCase):
    def test_publish_approved_slice_schedules_matrix(self) -> None:
        from services.slice_publish import publish_approved_slice

        item = {
            "review_id": "rev-s1",
            "run_id": "run-sp",
            "video_path": "/tmp/s1.mp4",
            "script": "切片脚本",
            "title": "切片S1",
            "payload": {
                "batch": "slice_drafts",
                "slice_id": "S1",
                "platform": "douyin",
                "keyword": "A面膜",
            },
        }
        with patch("services.publish.scheduler.schedule_publish", return_value={"ok": True, "job_id": "j1"}), patch(
            "services.matrix_strategy.auto_matrix_publish",
            return_value={"ok": True, "queued": 2},
        ), patch(
            "services.post_publish_monitor.schedule_monitor",
            return_value={"ok": True, "monitor_id": "mon-1"},
        ):
            out = publish_approved_slice(item)
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("slice_id"), "S1")
        self.assertTrue((out.get("matrix") or {}).get("ok"))

    def test_approve_review_triggers_slice_publish(self) -> None:
        from services.feishu_review import review_token
        from services.review_queue import approve_review, submit_batch_for_review

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "sp.db"
            v = Path(td) / "v.mp4"
            v.write_bytes(b"x")
            with patch("core.storage.DB_PATH", db), patch(
                "services.slice_publish.publish_approved_slice",
                return_value={"ok": True, "slice_id": "S1", "matrix": {"ok": True}},
            ) as mock_pub, patch("services.feishu_review.send_review_card", return_value={"ok": True}):
                from core.storage import init_storage

                init_storage()
                batch = submit_batch_for_review(
                    run_id="run-approve",
                    items=[{
                        "video_path": str(v),
                        "script": "s",
                        "title": "S1",
                        "payload": {"batch": "slice_drafts", "slice_id": "S1", "platform": "douyin"},
                    }],
                    notify_feishu=False,
                )
                rid = batch["review_ids"][0]
                out = approve_review(review_id=rid, token=review_token(rid))
            self.assertTrue(out.get("ok"))
            mock_pub.assert_called_once()


class FeishuApproveAllTest(unittest.TestCase):
    def test_batch_card_has_approve_all_button(self) -> None:
        from services.feishu_review import build_slice_batch_review_card, review_token

        items = [
            {"review_id": "rev-s1", "slice_id": "S1", "script": "a", "video_path": "a.mp4", "hook_style": "痛点反问"},
            {"review_id": "rev-s2", "slice_id": "S2", "script": "b", "video_path": "b.mp4", "hook_style": "结果先行"},
        ]
        with patch.dict("os.environ", {"REVIEW_FEISHU_USE_CALLBACK": "1"}):
            card = build_slice_batch_review_card(run_id="run-all", title="测试", items=items)
        actions = card["card"]["elements"][-1]["actions"]
        self.assertEqual(actions[0]["value"]["action"], "approve_all_slices")
        self.assertEqual(actions[0]["value"]["token"], review_token("batch-run-all"))

    def test_handle_approve_all_callback(self) -> None:
        from services.feishu_review import handle_review_callback, review_token

        run_id = "run-cb"
        token = review_token(f"batch-{run_id}")
        with patch(
            "services.slice_publish.approve_all_pending_slices",
            return_value={"ok": True, "approved": 3, "total": 3},
        ):
            out = handle_review_callback({
                "type": "card.action.trigger",
                "action": {"value": {"action": "approve_all_slices", "run_id": run_id, "token": token}},
            })
        self.assertIn("toast", out)
        self.assertEqual(out["toast"]["type"], "success")


class PlaywrightDockerTest(unittest.TestCase):
    def test_playwright_dockerfile_exists(self) -> None:
        self.assertTrue((ROOT / "Dockerfile.playwright").is_file())
        content = (ROOT / "Dockerfile.playwright").read_text(encoding="utf-8")
        self.assertIn("playwright", content.lower())

    def test_compose_playwright_profile(self) -> None:
        content = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("matrix-playwright", content)
        self.assertIn("profiles:", content)


if __name__ == "__main__":
    unittest.main()
