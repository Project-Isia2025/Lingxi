"""Phase28：公网隧道 + Playwright 发布联调验收。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


class TunnelTest(unittest.TestCase):
    def test_tunnel_status(self) -> None:
        from services.tunnel import review_callback_url, tunnel_status

        with patch.dict("os.environ", {"REVIEW_BASE_URL": "http://127.0.0.1:9100"}):
            st = tunnel_status(port=9100)
        self.assertTrue(st.get("ok"))
        self.assertTrue(st.get("needs_tunnel"))
        self.assertIn("/api/review/callback", review_callback_url("https://abc.ngrok.io"))

    def test_parse_cloudflared_url(self) -> None:
        from services.tunnel import parse_cloudflared_url

        text = "INF |  https://foo-bar.trycloudflare.com  |  ..."
        self.assertEqual(parse_cloudflared_url(text), "https://foo-bar.trycloudflare.com")

    def test_tunnel_api(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/api/tunnel/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("ok"))


class PublishReadinessTest(unittest.TestCase):
    def test_all_publish_readiness(self) -> None:
        from services.publish_readiness import all_publish_readiness

        out = all_publish_readiness()
        self.assertTrue(out.get("ok"))
        self.assertGreaterEqual(len(out.get("platforms") or []), 3)

    def test_dry_run_publish(self) -> None:
        import tempfile

        from services.publish_readiness import dry_run_publish_check

        with tempfile.TemporaryDirectory() as td:
            video = Path(td) / "v.mp4"
            video.write_bytes(b"x" * 1200)
            out = dry_run_publish_check(
                platform="douyin",
                video_path=str(video),
                script="测试口播",
                title="标题",
            )
        self.assertTrue(out.get("ok"))


class PublishE2eTest(unittest.TestCase):
    def test_publish_e2e_script(self) -> None:
        from scripts.acceptance_publish_e2e import run_publish_e2e

        out = run_publish_e2e()
        self.assertTrue(out.get("ok"), out.get("steps"))


if __name__ == "__main__":
    unittest.main()
