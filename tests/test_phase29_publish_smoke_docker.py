"""Phase29：Playwright 上传页 smoke + Docker full stack。"""
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


class ComposeProfilesTest(unittest.TestCase):
    def test_resolve_full_stack(self) -> None:
        from services.compose_profiles import compose_status, resolve_profiles

        self.assertEqual(resolve_profiles("full"), ["playwright", "tunnel"])
        st = compose_status()
        self.assertTrue(st.get("ok"))
        self.assertTrue(st.get("full_stack_ready"))

    def test_compose_api(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/api/docker/compose/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("full_stack_ready"))


class PublishSmokeTest(unittest.TestCase):
    def test_probe_without_storage(self) -> None:
        from services.publish_smoke import probe_publish_upload

        with patch("services.publish_smoke.resolve_storage", return_value=""):
            out = probe_publish_upload(platform="douyin")
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "storage_state_missing")

    def test_probe_success_mocked(self) -> None:
        from services.publish_smoke import probe_publish_upload

        with tempfile.TemporaryDirectory() as td:
            video = Path(td) / "v.mp4"
            video.write_bytes(b"x" * 1200)
            state = Path(td) / "state.json"
            state.write_text("{}", encoding="utf-8")
            with patch("services.publish_smoke.resolve_storage", return_value=str(state)), patch(
                "services.publish_smoke.playwright_installed",
                return_value=True,
            ), patch(
                "services.publish_smoke.publish_enabled",
                return_value=True,
            ), patch(
                "services.publish.creator_engine.run_publish",
                return_value={"success": True, "probe": True, "platform": "douyin"},
            ):
                out = probe_publish_upload(platform="douyin", video_path=str(video))
        self.assertTrue(out.get("ok"))
        self.assertTrue(out.get("probe"))


class PublishSmokeAcceptanceTest(unittest.TestCase):
    def test_check_only_mode(self) -> None:
        from scripts.acceptance_publish_smoke import run_publish_smoke_acceptance

        out = run_publish_smoke_acceptance(live_probe=False)
        self.assertTrue(out.get("ok"))


class CreatorEngineProbeTest(unittest.TestCase):
    def test_run_publish_has_probe_only(self) -> None:
        import inspect

        from services.publish.creator_engine import run_publish

        params = inspect.signature(run_publish).parameters
        self.assertIn("probe_only", params)


if __name__ == "__main__":
    unittest.main()
