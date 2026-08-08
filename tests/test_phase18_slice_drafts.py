"""Phase18：3×15s 独立成片初稿 + 商品图合成。"""
from __future__ import annotations

import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


class SliceDraftsContentTest(unittest.TestCase):
    def test_generate_slice_drafts_three_items(self) -> None:
        from services.slice_drafts import generate_slice_drafts

        strategy = {
            "variants": [
                {"id": "S1", "hook_style": "痛点反问", "brief": "切片1"},
                {"id": "S2", "hook_style": "结果先行", "brief": "切片2"},
                {"id": "S3", "hook_style": "对比冲击", "brief": "切片3"},
            ],
            "daily_directive": {"primary_product": {"name": "A款面膜"}},
        }
        out = generate_slice_drafts(
            base_script="测试口播稿。第一句痛点。第二句解决方案。",
            keyword="A面膜",
            strategy=strategy,
            product_name="A款面膜",
        )
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("count"), 3)
        drafts = out.get("drafts") or []
        self.assertEqual(len(drafts), 3)
        for d in drafts:
            self.assertEqual(d.get("duration_sec"), 15)
            self.assertEqual(d.get("structure"), "痛点+解决方案")
            self.assertTrue(d.get("script"))
            self.assertTrue((d.get("mix_plan") or {}).get("timeline"))

    def test_build_slice_mix_plan_duration(self) -> None:
        from services.slice_drafts import build_slice_mix_plan

        plan = build_slice_mix_plan(script="测试", keyword="护肤", slice_id="S1")
        self.assertAlmostEqual(plan.get("total_duration_sec"), 15.0, delta=1.0)
        self.assertEqual(plan.get("structure"), "痛点+解决方案")

    def test_generate_content_includes_slice_drafts(self) -> None:
        from services.content import generate_content

        strategy = {
            "variants": [
                {"id": "S1", "hook_style": "痛点反问"},
                {"id": "S2", "hook_style": "结果先行"},
                {"id": "S3", "hook_style": "对比冲击"},
            ],
            "inventory_product": {"name": "A款面膜"},
        }
        out = generate_content(
            source="素材测试",
            keyword="A面膜",
            angle="痛点+解决方案",
            memory={"forbidden_rows": [], "geo": {}},
            strategy=strategy,
            run_id="run-slice",
        )
        sd = out.get("slice_drafts") or {}
        self.assertTrue(sd.get("ok"))
        self.assertEqual(sd.get("count"), 3)
        self.assertEqual(len(out.get("variants") or []), 3)


class SliceDraftsRenderTest(unittest.TestCase):
    def test_render_slice_drafts_mock(self) -> None:
        from services.slice_drafts import generate_slice_drafts, render_slice_drafts

        strategy = {
            "variants": [
                {"id": "S1", "hook_style": "痛点反问"},
                {"id": "S2", "hook_style": "结果先行"},
                {"id": "S3", "hook_style": "对比冲击"},
            ],
        }
        pack = generate_slice_drafts(
            base_script="测试脚本内容。",
            keyword="护肤",
            strategy=strategy,
        )
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src.mp4"
            src.write_bytes(b"fake")
            with patch("services.slice_drafts.render_mix_video") as mock_render:
                mock_render.side_effect = lambda **kw: {
                    "ok": True,
                    "output_path": str(Path(td) / f"out_{kw.get('output_name')}.mp4"),
                }
                out = render_slice_drafts(
                    drafts=pack["drafts"],
                    source_video=str(src),
                    run_id="run-r1",
                    keyword="护肤",
                )
            self.assertTrue(out.get("ok"))
            self.assertEqual(out.get("count"), 3)


class ReviewBatchTest(unittest.TestCase):
    def test_submit_batch_for_review(self) -> None:
        from services.review_queue import submit_batch_for_review

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "r.db"
            v1 = Path(td) / "a.mp4"
            v2 = Path(td) / "b.mp4"
            v1.write_bytes(b"x")
            v2.write_bytes(b"y")
            with patch("core.storage.DB_PATH", db), patch(
                "services.feishu_review.send_review_card",
                return_value={"ok": True},
            ):
                from core.storage import init_storage

                init_storage()
                out = submit_batch_for_review(
                    run_id="run-batch",
                    items=[
                        {"video_path": str(v1), "script": "脚本1", "title": "切片1"},
                        {"video_path": str(v2), "script": "脚本2", "title": "切片2"},
                    ],
                    notify_feishu=False,
                )
            self.assertTrue(out.get("ok"))
            self.assertEqual(out.get("count"), 2)


class ProductComposeTest(unittest.TestCase):
    def test_resolve_product_image_from_extra(self) -> None:
        from services.product_compose import resolve_product_image

        with tempfile.TemporaryDirectory() as td:
            img = Path(td) / "prod.png"
            img.write_bytes(b"png")
            path = resolve_product_image(extra={"product_image": str(img)})
            self.assertEqual(path, str(img.resolve()))


class ExecutionSliceIntegrationTest(unittest.TestCase):
    @patch("services.execution.deploy_ad_plan", return_value=None)
    @patch("services.execution.quality_gate", return_value={"passed": True})
    @patch("services.feishu_review.send_review_card", return_value={"ok": True})
    def test_build_execution_submits_slice_batch(self, _card, mock_qg, _ad) -> None:
        from services.execution import build_execution

        goal = MagicMock()
        goal.video_path = ""
        goal.platform = "douyin"
        goal.keyword = "护肤"
        goal.title = "测试"
        goal.video_provider = "template"
        goal.auto_publish = False
        goal.auto_execute = False
        goal.auto_matrix_publish = False
        goal.budget_limit = 0
        goal.extra = {"source_video": "D:/videos/demo.mp4"}

        content = {
            "script": "测试脚本",
            "channel_contents": {"short_video_script": "测试"},
            "risk_check": {"passed": True},
            "slice_drafts": {
                "ok": True,
                "drafts": [
                    {"id": "S1", "script": "a", "mix_plan": {"timeline": [{}]}},
                    {"id": "S2", "script": "b", "mix_plan": {"timeline": [{}]}},
                ],
            },
        }
        strategy = {"target_platform": "douyin", "primary_keyword": "护肤", "channels": ["short_video"]}

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "e.db"
            with patch("core.storage.DB_PATH", db), patch(
                "services.execution._maybe_render_slice_drafts",
                return_value={
                    "ok": True,
                    "recommended_path": str(Path(td) / "rec.mp4"),
                    "renders": [
                        {"id": "S1", "output_path": str(Path(td) / "s1.mp4"), "script": "a"},
                        {"id": "S2", "output_path": str(Path(td) / "s2.mp4"), "script": "b"},
                    ],
                },
            ), patch("services.execution._maybe_render_video", return_value=("", None)):
                Path(td, "s1.mp4").write_bytes(b"1")
                Path(td, "s2.mp4").write_bytes(b"2")
                Path(td, "rec.mp4").write_bytes(b"r")
                from core.storage import init_storage

                init_storage()
                out = build_execution(
                    run_id=f"run-{uuid.uuid4().hex[:6]}",
                    goal=goal,
                    strategy=strategy,
                    content=content,
                    exec_url="",
                )
        review = out.get("review") or {}
        self.assertTrue(review.get("ok"))
        self.assertGreaterEqual(review.get("count", 0), 2)


if __name__ == "__main__":
    unittest.main()
