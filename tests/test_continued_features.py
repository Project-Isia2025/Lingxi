"""投流 ROI 闭环、小红书正文、TTS 测试。"""
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


class AdFeedbackTest(unittest.TestCase):
    def test_compute_ad_roi_score(self) -> None:
        from services.ad_feedback import compute_ad_roi_score

        score = compute_ad_roi_score({"impressions": 2000, "clicks": 50, "cost_cny": 80, "ctr": 0.025})
        self.assertGreater(score, 0.4)

    def test_sync_ad_report_dry_run(self) -> None:
        from core.storage import save_ad_campaign
        from services.ad_feedback import sync_ad_report_for_run

        save_ad_campaign(run_id="test-run-ad", campaign_id="dry_abc123", keyword="护肤", dry_run=True)
        out = sync_ad_report_for_run("test-run-ad")
        self.assertTrue(out.get("ok"))
        self.assertIn("ad_roi_score", out)
        self.assertIn("metrics", out)


class XhsNoteDetailTest(unittest.TestCase):
    @patch("services.xhs.note_detail._fetch_note_page")
    def test_fetch_note_detail(self, mock_fetch) -> None:
        mock_fetch.return_value = (
            {
                "note_id": "abc123def456789012345678",
                "url": "https://www.xiaohongshu.com/explore/abc123def456789012345678",
                "title": "深度笔记",
                "body": "这是完整正文内容，包含产品测评与使用心得。",
                "tags": ["护肤", "测评"],
                "likes": 3200,
            },
            False,
        )
        with patch("services.xhs.note_detail.xc.resolve_storage_state", return_value="/fake.json"):
            from services.xhs.note_detail import fetch_note_detail

            out = fetch_note_detail("abc123def456789012345678")
        self.assertTrue(out.get("ok"))
        self.assertIn("完整正文", out.get("body", ""))

    @patch("services.xhs.note_detail.fetch_note_detail")
    def test_enrich_competitors(self, mock_detail) -> None:
        mock_detail.return_value = {
            "ok": True,
            "body": "正文",
            "tags": ["标签"],
            "title": "标题",
            "likes": 100,
        }
        from services.xhs.note_detail import enrich_competitors

        comps = [{"platform": "xiaohongshu", "note_id": "abc123def456789012345678", "url": "https://xhs/explore/abc"}]
        out = enrich_competitors(comps, limit=1)
        self.assertTrue(out[0].get("detail_fetched"))


class TtsTest(unittest.TestCase):
    @patch("services.tts._edge_tts_available", return_value=False)
    @patch("services.tts._ffmpeg_silent")
    def test_synthesize_fallback(self, mock_silent, _edge) -> None:
        out_path = ROOT / "data" / "output" / "test_tts.mp3"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        def _write(path, dur, ff):
            Path(path).write_bytes(b"ID3")

        mock_silent.side_effect = _write
        from services.tts import synthesize_speech

        out = synthesize_speech("测试口播文案", output_path=out_path, duration_hint_sec=5)
        self.assertTrue(out.get("ok"))
        self.assertIn(out.get("provider"), ("silent_fallback", "edge_tts", "openai_compatible"))


class VideoMixTtsTest(unittest.TestCase):
    @patch("services.video_mix._attach_tts")
    @patch("services.video_mix.subprocess.run")
    @patch("services.video_mix.resolve_ffmpeg", return_value="ffmpeg")
    def test_render_with_tts(self, _ff, mock_run, mock_tts) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        mock_tts.return_value = {"ok": True, "output_path": str(ROOT / "data" / "output" / "videos" / "mix_voiced.mp4")}
        from services.video_mix import build_mix_plan, render_mix_video

        src = ROOT / "data" / "test_src.mp4"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(b"\x00")
        plan = build_mix_plan(script="测试脚本内容。" * 10, keyword="护肤")
        out_path = ROOT / "data" / "output" / "videos"
        out_path.mkdir(parents=True, exist_ok=True)
        with patch("services.video_mix.output_dir", return_value=out_path):
            out = render_mix_video(
                mix_plan=plan,
                source_video=str(src),
                run_id="ttsrun",
                script="测试口播配音",
                enable_tts=True,
            )
        self.assertTrue(out.get("ok"))
        mock_tts.assert_called_once()


class DeployAdPlanTest(unittest.TestCase):
    def test_deploy_saves_campaign(self) -> None:
        from services.ad_optimizer import deploy_ad_plan

        plan = {"keyword": "护肤", "platform": "douyin", "daily_budget_cny": 100}
        out = deploy_ad_plan(plan, run_id="deploy-test-1", sync_api=True)
        self.assertTrue(out.get("campaign_id"))
        from core.storage import get_ad_campaign_by_run

        row = get_ad_campaign_by_run("deploy-test-1")
        self.assertIsNotNone(row)


if __name__ == "__main__":
    unittest.main()
