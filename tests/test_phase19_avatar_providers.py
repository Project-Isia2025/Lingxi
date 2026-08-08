"""Phase19：Avatar/Volc/Kling 适配器 + CLI 切片模式 + E2E 烟测。"""
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


class AvatarProviderTest(unittest.TestCase):
    def test_build_payload_includes_clone(self) -> None:
        from services.video_providers.avatar import build_payload

        with patch.dict("os.environ", {"AVATAR_CLONE_ID": "clone-1", "AVATAR_VOICE_ID": "voice-1"}):
            payload = build_payload(script="测试口播", run_id="r1", image_path="/img.png")
        self.assertEqual(payload.get("avatar_id"), "clone-1")
        self.assertEqual(payload.get("voice_id"), "voice-1")
        self.assertEqual(payload.get("speech_text"), "测试口播")

    def test_mock_copy_source(self) -> None:
        from services.video_providers.avatar import produce

        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src.mp4"
            src.write_bytes(b"video")
            with patch("services.video_providers.http_client.api_credentials", return_value=("", "")):
                out = produce(script="测试", run_id="r2", source_video=str(src))
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("mode"), "mock")

    def test_mock_image_when_no_source(self) -> None:
        from services.video_providers.avatar import produce

        with tempfile.TemporaryDirectory() as td:
            img = Path(td) / "prod.png"
            img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)
            with patch("services.video_providers.http_client.api_credentials", return_value=("", "")):
                with patch("services.video_providers.avatar.mock_image_to_video") as mock_img:
                    mock_img.return_value = {"ok": True, "output_path": str(Path(td) / "out.mp4"), "mode": "mock_image"}
                    out = produce(script="测试", run_id="r3", image_path=str(img))
        self.assertTrue(out.get("ok"))


class ProviderRegistryTest(unittest.TestCase):
    def test_list_providers(self) -> None:
        from services.video_providers.router import list_providers, produce_video

        providers = list_providers()
        self.assertIn("avatar", providers)
        self.assertIn("volc", providers)
        self.assertIn("kling", providers)

        out = produce_video(provider="template", script="x", run_id="r")
        self.assertFalse(out.get("ok"))


class VolcKlingPayloadTest(unittest.TestCase):
    def test_volc_payload(self) -> None:
        from services.video_providers.volc import build_payload

        p = build_payload(script="口播", run_id="v1", image_path="/a.png", extra={"duration_sec": 15})
        self.assertEqual(p.get("text"), "口播")
        self.assertEqual(p.get("duration"), 15)

    def test_kling_payload(self) -> None:
        from services.video_providers.kling import build_payload

        p = build_payload(script="口播", run_id="k1", source_video="/v.mp4")
        self.assertEqual(p.get("prompt"), "口播")
        self.assertEqual(p.get("aspect_ratio"), "9:16")


class AcceptanceSliceE2eTest(unittest.TestCase):
    def test_e2e_script_runs(self) -> None:
        from scripts.acceptance_slice_e2e import run_e2e

        report = run_e2e(keyword="A面膜")
        self.assertGreaterEqual(report.get("passed", 0), 4)
        self.assertTrue(report.get("ok"))


if __name__ == "__main__":
    unittest.main()
