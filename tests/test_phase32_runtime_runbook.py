"""Phase32：运行时自启 + 生产联调 Runbook + 发布→监控链路。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


class RuntimeStatusTest(unittest.TestCase):
    def test_runtime_status(self) -> None:
        from services.runtime_status import runtime_status

        st = runtime_status()
        self.assertTrue(st.get("ok"))
        self.assertIn("api_health", st)
        self.assertIn("autostart", st)

    def test_runtime_api(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/api/runtime/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("ok"))


class PublishMonitorChainTest(unittest.TestCase):
    def test_chain_dry_run(self) -> None:
        from services.publish_monitor_chain import run_publish_monitor_chain

        out = run_publish_monitor_chain(live=False, platform="douyin")
        self.assertTrue(out.get("ok"), out.get("steps"))

    def test_acceptance_script(self) -> None:
        from scripts.acceptance_publish_monitor_live import run_publish_monitor_live

        out = run_publish_monitor_live(live=False)
        self.assertTrue(out.get("ok"))


class LiveRunbookTest(unittest.TestCase):
    def test_runbook_dry(self) -> None:
        from services.live_runbook import build_live_runbook

        out = build_live_runbook(live=False)
        self.assertTrue(out.get("ok"), out.get("steps"))

    def test_runbook_api(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/api/runtime/runbook?live=false")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("ok"))

    def test_acceptance_live_runbook(self) -> None:
        from services.live_runbook import build_live_runbook

        out = build_live_runbook(live=False)
        self.assertGreaterEqual(out.get("passed", 0), 7)


class SystemdTemplateTest(unittest.TestCase):
    def test_systemd_files_exist(self) -> None:
        unit = ROOT / "deploy" / "systemd" / "ai-agent-matrix.service"
        env = ROOT / "deploy" / "systemd" / "env.example"
        install = ROOT / "scripts" / "systemd_install.sh"
        self.assertTrue(unit.is_file())
        self.assertTrue(env.is_file())
        self.assertTrue(install.is_file())

    def test_systemd_status(self) -> None:
        from services.runtime_status import systemd_autostart_status

        st = systemd_autostart_status()
        self.assertTrue(st.get("template_ready"))


class DeployVerifySystemdTest(unittest.TestCase):
    def test_deploy_verify_systemd(self) -> None:
        from scripts.acceptance_deploy_verify import run_deploy_verify

        out = run_deploy_verify()
        steps = {s["step"]: s for s in out.get("steps") or []}
        self.assertTrue(steps.get("systemd_unit", {}).get("ok"))


if __name__ == "__main__":
    unittest.main()
