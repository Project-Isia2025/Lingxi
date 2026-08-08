"""Phase31：完播监控+下架 E2E + Helm Chart。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


class MonitorReadinessTest(unittest.TestCase):
    def test_readiness_status(self) -> None:
        from services.monitor_readiness import monitor_readiness_status

        st = monitor_readiness_status(platform="douyin")
        self.assertTrue(st.get("ok"))
        self.assertTrue(st.get("monitor_enabled"))
        self.assertTrue(st.get("takedown_dry_run"))

    def test_readiness_api(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/api/monitor/readiness")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("monitor_enabled"))


class MonitorE2ETest(unittest.TestCase):
    def test_acceptance_monitor_e2e(self) -> None:
        from scripts.acceptance_monitor_e2e import run_monitor_e2e

        out = run_monitor_e2e()
        self.assertTrue(out.get("ok"), out.get("steps"))


class HelmChartTest(unittest.TestCase):
    def test_helm_validate(self) -> None:
        from services.deploy_status import helm_chart_status, validate_helm_chart

        chart = helm_chart_status()
        validation = validate_helm_chart()
        self.assertTrue(chart.get("ok"))
        self.assertTrue(validation.get("ok"))

    def test_helm_api(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/api/deploy/helm/status")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertTrue(body.get("chart", {}).get("ok"))


class DeployVerifyHelmTest(unittest.TestCase):
    def test_deploy_verify_includes_helm(self) -> None:
        from scripts.acceptance_deploy_verify import run_deploy_verify

        out = run_deploy_verify()
        self.assertTrue(out.get("ok"))
        steps = {s["step"]: s for s in out.get("steps") or []}
        self.assertTrue(steps.get("helm_chart", {}).get("ok"))


if __name__ == "__main__":
    unittest.main()
