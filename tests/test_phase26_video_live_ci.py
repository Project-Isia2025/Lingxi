"""Phase26：视频 Provider 联调 + GitHub Actions CI。"""
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


class VideoProviderStatusTest(unittest.TestCase):
    def test_all_providers_status(self) -> None:
        from services.video_provider_status import all_providers_status, provider_status

        with patch.dict("os.environ", {"AVATAR_API_KEY": "", "AVATAR_API_URL": ""}, clear=False):
            st = provider_status("avatar")
        self.assertEqual(st["provider"], "avatar")
        self.assertEqual(st["mode"], "mock")

        summary = all_providers_status()
        self.assertTrue(summary.get("ok"))
        self.assertIn("avatar", [p["provider"] for p in summary["providers"]])

    def test_configured_mode(self) -> None:
        from services.video_provider_status import provider_status

        with patch.dict(
            "os.environ",
            {"AVATAR_API_KEY": "sk-test-key", "AVATAR_API_URL": "https://api.example.com/v1/video"},
        ):
            st = provider_status("avatar")
        self.assertTrue(st["configured"])
        self.assertEqual(st["mode"], "live")
        self.assertIn("***", st["key_preview"])


class VideoLiveAcceptanceTest(unittest.TestCase):
    def test_dry_run_all_providers(self) -> None:
        from scripts.acceptance_video_live import run_video_acceptance

        out = run_video_acceptance(live=False)
        self.assertTrue(out.get("ok"), out.get("steps"))
        self.assertGreaterEqual(out.get("passed", 0), 4)

    def test_live_requires_confirm(self) -> None:
        from scripts.acceptance_video_live import run_video_acceptance

        out = run_video_acceptance(live=True, confirm=False)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "live_requires_confirm")

    def test_api_providers_status_endpoint(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/api/video/providers/status")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertIn("providers", body)


class CiWorkflowTest(unittest.TestCase):
    def test_github_workflow_exists(self) -> None:
        wf = ROOT / ".github" / "workflows" / "ci.yml"
        self.assertTrue(wf.is_file())
        text = wf.read_text(encoding="utf-8")
        self.assertIn("acceptance_all.py", text)
        self.assertIn("acceptance_video_live.py", text)


if __name__ == "__main__":
    unittest.main()
