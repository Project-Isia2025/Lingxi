"""Phase33：运维 Dashboard + E2E 联调手册。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


class RuntimeDashboardTest(unittest.TestCase):
    def test_build_dashboard(self) -> None:
        from services.runtime_dashboard import E2E_GUIDE_PHASES, build_runtime_dashboard

        dash = build_runtime_dashboard(platform="douyin")
        self.assertTrue(dash.get("ok"))
        self.assertGreaterEqual(len(dash.get("cards") or []), 5)
        self.assertGreaterEqual(len(dash.get("runbook_checklist") or []), 7)
        self.assertEqual(len(E2E_GUIDE_PHASES), 6)

    def test_runtime_dashboard_api(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/api/dashboard/runtime")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertTrue(body.get("guide"))

    def test_runtime_dashboard_page(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/dashboard/runtime")
        self.assertEqual(r.status_code, 200)
        self.assertIn("运维中心", r.text)
        self.assertIn("联调 Runbook", r.text)


class RuntimeDashboardAcceptanceTest(unittest.TestCase):
    def test_acceptance_script(self) -> None:
        from scripts.acceptance_runtime_dashboard import run_runtime_dashboard_acceptance

        out = run_runtime_dashboard_acceptance()
        self.assertTrue(out.get("ok"), out.get("steps"))


if __name__ == "__main__":
    unittest.main()
