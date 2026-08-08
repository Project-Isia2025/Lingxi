"""Phase27：飞书回调 E2E + Playwright 登录态向导。"""
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


class FeishuReviewStatusTest(unittest.TestCase):
    def test_feishu_status(self) -> None:
        from services.feishu_review_status import feishu_review_status

        with patch.dict("os.environ", {"REVIEW_FEISHU_WEBHOOK_URL": "https://hook.example.com/abc"}):
            st = feishu_review_status()
        self.assertTrue(st.get("ok"))
        self.assertTrue(st.get("webhook_configured"))
        self.assertIn("/api/review/callback", st.get("callback_url") or "")


class FeishuE2eTest(unittest.TestCase):
    def test_feishu_callback_flow(self) -> None:
        from scripts.acceptance_feishu_e2e import run_feishu_e2e

        out = run_feishu_e2e(run_id="test-feishu-run")
        self.assertTrue(out.get("ok"), out.get("steps"))
        self.assertGreaterEqual(out.get("passed", 0), 7)


class StorageWizardTest(unittest.TestCase):
    def test_all_storage_status(self) -> None:
        from services.storage_state_wizard import all_storage_status, inspect_storage_file

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "state.json"
            p.write_text(json.dumps({"cookies": [{"name": "a", "value": "b"}], "origins": []}), encoding="utf-8")
            info = inspect_storage_file(p)
            self.assertTrue(info.get("valid"))

        summary = all_storage_status()
        self.assertTrue(summary.get("ok"))
        self.assertIn("douyin_creator", [t["id"] for t in summary["targets"]])

    def test_storage_status_api(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/api/storage/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("ok"))

    def test_feishu_status_api(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/api/review/feishu/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("ok"))


class ExportWizardCliTest(unittest.TestCase):
    def test_list_targets(self) -> None:
        from services.storage_state_wizard import STORAGE_TARGETS

        self.assertIn("douyin_creator", STORAGE_TARGETS)
        self.assertIn("xhs_creator", STORAGE_TARGETS)


if __name__ == "__main__":
    unittest.main()
