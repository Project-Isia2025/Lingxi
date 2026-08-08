"""Phase25：一键验收脚本整合。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


class ApiSmokeTest(unittest.TestCase):
    def test_api_smoke_passes(self) -> None:
        from scripts.acceptance_api_smoke import run_api_smoke

        out = run_api_smoke()
        self.assertTrue(out.get("ok"), out.get("steps"))
        self.assertGreaterEqual(out.get("passed", 0), 8)

    def test_health_endpoint(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("ok"))


class AcceptanceAllTest(unittest.TestCase):
    def test_run_acceptance_all_fast(self) -> None:
        from scripts.acceptance_all import run_acceptance_all

        report = run_acceptance_all(
            skip_pytest=True,
            skip_spec=False,
            skip_e2e=False,
            skip_api=False,
            skip_docker=True,
        )
        summary = report.summary()
        self.assertTrue(summary["ok"], [(s.name, s.status, s.detail) for s in report.stages if s.status == "FAIL"])


class DockerSmokeTest(unittest.TestCase):
    def test_docker_smoke_runs(self) -> None:
        from scripts.acceptance_docker_smoke import run_docker_smoke

        out = run_docker_smoke(live=False)
        # docker 未安装时 skipped=True 也算通过
        self.assertTrue(out.get("ok") or out.get("skipped"))


if __name__ == "__main__":
    unittest.main()
