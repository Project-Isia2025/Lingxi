"""Phase20：飞书 3 切片合并审核卡片 + Docker 部署。"""
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


class FeishuBatchCardTest(unittest.TestCase):
    def test_build_slice_batch_card_three_slices(self) -> None:
        from services.feishu_review import build_slice_batch_review_card, review_token

        items = []
        for sid, hook in [("S1", "痛点反问"), ("S2", "结果先行"), ("S3", "对比冲击")]:
            rid = f"rev-{sid}"
            items.append({
                "review_id": rid,
                "slice_id": sid,
                "hook_style": hook,
                "script": f"脚本{sid}",
                "video_path": f"/tmp/{sid}.mp4",
                "token": review_token(rid),
            })

        with patch.dict("os.environ", {"REVIEW_FEISHU_USE_CALLBACK": "1"}):
            card = build_slice_batch_review_card(
                run_id="run-batch",
                title="A面膜",
                items=items,
                keyword="A面膜",
            )

        elements = card["card"]["elements"]
        action_blocks = [e for e in elements if e.get("tag") == "action"]
        self.assertEqual(len(action_blocks), 4)
        self.assertEqual(action_blocks[0]["actions"][0]["value"]["slice_id"], "S1")
        self.assertEqual(action_blocks[-1]["actions"][0]["value"]["action"], "approve_all_slices")
        self.assertIn("3 条切片审核", card["card"]["header"]["title"]["content"])

    def test_batch_submit_sends_one_card(self) -> None:
        from services.review_queue import submit_batch_for_review

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "b.db"
            paths = []
            for i in range(3):
                p = Path(td) / f"v{i}.mp4"
                p.write_bytes(b"x")
                paths.append(str(p))
            with patch("core.storage.DB_PATH", db), patch(
                "services.feishu_review.send_review_card",
                return_value={"ok": True},
            ) as mock_send:
                from core.storage import init_storage

                init_storage()
                out = submit_batch_for_review(
                    run_id="run-feishu-batch",
                    items=[
                        {
                            "video_path": paths[i],
                            "script": f"s{i}",
                            "title": f"切片{i+1}",
                            "payload": {"slice_id": f"S{i+1}", "keyword": "A面膜", "platform": "douyin"},
                        }
                        for i in range(3)
                    ],
                )
            self.assertTrue(out.get("ok"))
            self.assertTrue(out.get("batch_card"))
            self.assertEqual(out.get("count"), 3)
            mock_send.assert_called_once()


class DockerDeployTest(unittest.TestCase):
    def test_docker_files_exist(self) -> None:
        self.assertTrue((ROOT / "Dockerfile").is_file())
        self.assertTrue((ROOT / "docker-compose.yml").is_file())
        self.assertTrue((ROOT / "scripts" / "docker_up.py").is_file())

    def test_dockerfile_mentions_ffmpeg(self) -> None:
        content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("ffmpeg", content)
        self.assertIn("9100", content)


if __name__ == "__main__":
    unittest.main()
