"""Phase30：真实发布 submit + 生产部署模板。"""
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


class DeployStatusTest(unittest.TestCase):
    def test_manifest_ready(self) -> None:
        from services.deploy_status import deploy_manifest_status, validate_k8s_yaml

        m = deploy_manifest_status()
        self.assertTrue(m.get("docker_prod_ready"))
        self.assertTrue(m.get("k8s_ready"))
        self.assertTrue(validate_k8s_yaml().get("ok"))

    def test_deploy_api(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/api/deploy/status")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertTrue(body.get("manifest", {}).get("docker_prod_ready"))


class SubmitGuardTest(unittest.TestCase):
    def test_submit_requires_confirm(self) -> None:
        from services.publish_smoke import probe_publish_upload

        out = probe_publish_upload(platform="douyin", submit=True, confirm=False)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "submit_requires_confirm")


class DeployVerifyTest(unittest.TestCase):
    def test_acceptance_deploy_verify(self) -> None:
        from scripts.acceptance_deploy_verify import run_deploy_verify

        out = run_deploy_verify()
        self.assertTrue(out.get("ok"), out.get("steps"))


if __name__ == "__main__":
    unittest.main()
