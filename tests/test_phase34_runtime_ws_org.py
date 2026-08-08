"""Phase34：运维 WebSocket 实时推送 + 多 org 过滤。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


class OrgCatalogTest(unittest.TestCase):
    def test_org_catalog(self) -> None:
        from services.org_catalog import list_org_ids, org_catalog_status

        st = org_catalog_status()
        self.assertTrue(st.get("ok"))
        self.assertIsInstance(list_org_ids(), list)


class RuntimeOrgDashboardTest(unittest.TestCase):
    def test_build_with_org(self) -> None:
        from services.runtime_dashboard import build_runtime_dashboard

        dash = build_runtime_dashboard(platform="douyin", org_id="org-a")
        self.assertTrue(dash.get("ok"))
        self.assertEqual(dash.get("org_id"), "org-a")
        self.assertIn("org_queue", dash)
        self.assertIn("org_monitor", dash)

    def test_org_catalog_api(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/api/orgs/catalog")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("ok"))


class RuntimeWebSocketTest(unittest.TestCase):
    def test_ws_status_includes_runtime(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/api/dashboard/ws/status")
        self.assertEqual(r.status_code, 200)
        self.assertIn("runtime_connections", r.json())

    def test_runtime_ws_connect(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        with client.websocket_connect("/ws/dashboard/runtime?platform=douyin&org_id=org-test") as ws:
            msg = ws.receive_json()
            self.assertEqual(msg.get("channel"), "runtime")
            self.assertTrue(msg.get("ok"))
            self.assertEqual(msg.get("org_id"), "org-test")
            ws.send_text("refresh")
            msg2 = ws.receive_json()
            self.assertEqual(msg2.get("event"), "update")


class DashboardHubRuntimeTest(unittest.TestCase):
    def test_runtime_connection_count(self) -> None:
        from services.dashboard_hub import broadcast_runtime, runtime_connection_count

        self.assertEqual(runtime_connection_count(), 0)

        async def _run() -> None:
            await broadcast_runtime(reason="test")

        import asyncio

        asyncio.run(_run())


class RuntimeWsOrgAcceptanceTest(unittest.TestCase):
    def test_acceptance_script(self) -> None:
        from scripts.acceptance_runtime_ws_org import run_runtime_ws_org_acceptance

        out = run_runtime_ws_org_acceptance()
        self.assertTrue(out.get("ok"), out.get("steps"))


if __name__ == "__main__":
    unittest.main()
