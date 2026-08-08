"""Phase35：多 org Webhook + Runbook 告警。"""
from __future__ import annotations

import json
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


class OrgWebhookConfigTest(unittest.TestCase):
    def test_resolve_org_webhook(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "org_webhooks.json"
            path.write_text(
                json.dumps(
                    {
                        "orgs": {
                            "org-a": {
                                "enabled": True,
                                "review_webhook_url": "https://example.com/review",
                                "runbook_webhook_url": "https://example.com/runbook",
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch("services.org_webhook_config.org_webhooks_path", return_value=path):
                from services.org_webhook_config import resolve_webhook, upsert_org_config

                self.assertEqual(resolve_webhook("org-a", "review"), "https://example.com/review")
                self.assertEqual(resolve_webhook("org-a", "runbook"), "https://example.com/runbook")
                out = upsert_org_config("org-b", {"label": "B", "alert_webhook_url": "https://x/y"})
                self.assertTrue(out.get("ok"))


class RunbookAlertTest(unittest.TestCase):
    def test_extract_failures(self) -> None:
        from services.runbook_alert import build_runbook_alert_payload, dispatch_runbook_alert

        runbook = {
            "ok": False,
            "passed": 7,
            "total": 9,
            "steps": [
                {"step": "a", "ok": True},
                {"step": "b", "ok": False, "detail": "missing webhook"},
            ],
        }
        payload = build_runbook_alert_payload(runbook=runbook, org_id="org-a")
        self.assertEqual(len(payload.get("alerts") or []), 1)
        out = dispatch_runbook_alert(runbook=runbook, org_id="org-a", dry_run=True)
        self.assertTrue(out.get("dry_run"))
        self.assertFalse(out.get("sent"))


class OrgWebhookApiTest(unittest.TestCase):
    def test_org_webhook_api(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/api/orgs/webhooks/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("ok"))

        r2 = client.get("/api/runtime/runbook/alert/status")
        self.assertEqual(r2.status_code, 200)
        self.assertIn("enabled", r2.json())

        r3 = client.post("/api/runtime/runbook/alert?dry_run=1&org_id=demo")
        self.assertEqual(r3.status_code, 200)
        self.assertTrue(r3.json().get("ok"))


class FeishuOrgWebhookTest(unittest.TestCase):
    def test_webhook_url_with_org(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "org_webhooks.json"
            path.write_text(
                json.dumps({"orgs": {"o1": {"review_webhook_url": "https://org-hook"}}}),
                encoding="utf-8",
            )
            with patch("services.org_webhook_config.org_webhooks_path", return_value=path):
                from services.feishu_review import webhook_url

                self.assertEqual(webhook_url("o1"), "https://org-hook")


class OrgWebhookAcceptanceTest(unittest.TestCase):
    def test_acceptance_script(self) -> None:
        from scripts.acceptance_org_webhook_alert import run_org_webhook_acceptance

        out = run_org_webhook_acceptance()
        self.assertTrue(out.get("ok"), out.get("steps"))


if __name__ == "__main__":
    unittest.main()
