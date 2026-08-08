"""HeyGen / CapCut Provider 与影刀 RPA Webhook 测试。"""
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


class HeyGenCapcutProviderTest(unittest.TestCase):
    def test_providers_registered(self) -> None:
        from services.video_providers.router import list_providers

        providers = list_providers()
        self.assertIn("heygen", providers)
        self.assertIn("capcut", providers)

    def test_heygen_mock_without_key(self) -> None:
        from services.video_providers.heygen import produce

        with patch.dict("os.environ", {"HEYGEN_API_KEY": "", "HEYGEN_API_URL": ""}, clear=False):
            out = produce(script="测试 HeyGen 口播脚本", run_id="t-heygen", source_video="")
        self.assertIn("ok", out)

    def test_capcut_mock_without_key(self) -> None:
        from services.video_providers.capcut import produce

        with patch.dict("os.environ", {"CAPCUT_API_KEY": "", "CAPCUT_API_URL": ""}, clear=False):
            out = produce(script="测试剪映模板口播", run_id="t-capcut", source_video="")
        self.assertIn("ok", out)

    def test_plan_video_cost_includes_new_providers(self) -> None:
        from services.strategy import plan_video_cost

        hg = plan_video_cost(provider="heygen", script="x" * 20)
        cc = plan_video_cost(provider="capcut", script="x" * 20)
        self.assertGreater(hg.get("estimated_cost", 0), 0)
        self.assertGreater(cc.get("estimated_cost", 0), 0)


class RpaWebhookTest(unittest.TestCase):
    def test_yingdao_chinese_field_mapping(self) -> None:
        from services.rpa_ingest import ingest_rpa_webhook, normalize_rpa_payload

        mapping = ROOT / "data" / "rpa_field_mapping.example.json"
        payload = {
            "keyword": "护肤",
            "items": [{"标题": "中文列名测试", "链接": "https://example.com/cn", "点赞数": 3000}],
        }
        with patch.dict("os.environ", {"RPA_FIELD_MAPPING_PATH": str(mapping)}, clear=False):
            norm = normalize_rpa_payload(payload, source="yingdao")
            self.assertEqual(norm["item_count"], 1)
            self.assertEqual(norm["items"][0]["title"], "中文列名测试")
            self.assertEqual(norm["items"][0]["likes"], 3000)

    def test_ingest_and_fetch(self) -> None:
        from services.rpa_ingest import fetch_rpa_competitors, ingest_rpa_webhook

        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "rpa.json"
            payload = {
                "platform": "douyin",
                "keyword": "护肤测试",
                "items": [
                    {"title": "RPA爆款1", "url": "https://example.com/1", "likes": 9000},
                    {"title": "RPA爆款2", "url": "https://example.com/2", "likes": 5000},
                ],
            }
            with patch.dict(
                "os.environ",
                {"RPA_INGEST_PATH": str(store), "RPA_WEBHOOK_SECRET": "", "RPA_INGEST_ENABLED": "1"},
            ):
                ing = ingest_rpa_webhook(payload, source="yingdao")
                self.assertTrue(ing.get("ok"))
                items, meta = fetch_rpa_competitors("护肤", "douyin", limit=5)
                self.assertEqual(len(items), 2)
                self.assertEqual(meta.get("source"), "rpa_webhook")

    def test_webhook_requires_token_when_configured(self) -> None:
        from services.rpa_ingest import ingest_rpa_webhook

        with patch.dict("os.environ", {"RPA_WEBHOOK_SECRET": "secret123"}, clear=False):
            bad = ingest_rpa_webhook({"items": [{"title": "x", "url": "u"}]}, token="wrong")
            good = ingest_rpa_webhook({"items": [{"title": "x", "url": "u"}]}, token="secret123")
        self.assertFalse(bad.get("ok"))
        self.assertTrue(good.get("ok"))

    def test_rpa_api_endpoints(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/api/rpa/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("ok"))

        with patch.dict("os.environ", {"RPA_WEBHOOK_SECRET": ""}, clear=False):
            r2 = client.post(
                "/api/rpa/webhook/yingdao",
                json={
                    "platform": "douyin",
                    "keyword": "api测试",
                    "items": [{"title": "API回写", "url": "https://example.com/a", "likes": 100}],
                },
            )
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.json().get("ok"))


    def test_rpa_dashboard_and_test_ingest(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/dashboard/rpa")
        self.assertEqual(r.status_code, 200)
        self.assertIn("影刀", r.text)

        g = client.get("/api/rpa/guide").json()
        self.assertTrue(g.get("ok"))
        self.assertGreaterEqual(len(g.get("yingdao_steps") or []), 3)

        init = client.post("/api/rpa/setup/init-mapping")
        self.assertEqual(init.status_code, 200)
        self.assertTrue(init.json().get("ok"))

        blocked = client.post("/api/rpa/test-ingest")
        self.assertEqual(blocked.status_code, 403)

        with patch.dict("os.environ", {"DEBUG": "1"}, clear=False):
            test = client.post("/api/rpa/test-ingest")
        self.assertEqual(test.status_code, 200)
        self.assertTrue(test.json().get("ok"))


class AliyunFcHandlerTest(unittest.TestCase):
    def test_fc_health_handler(self) -> None:
        import importlib.util

        path = ROOT / "deploy" / "aliyun-fc" / "handler.py"
        spec = importlib.util.spec_from_file_location("fc_handler_test", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        resp = mod.handler(
            {"rawPath": "/health", "requestContext": {"http": {"method": "GET"}}, "headers": {}, "body": ""},
            None,
        )
        self.assertEqual(resp.get("statusCode"), 200)
        body = json.loads(resp.get("body") or "{}")
        self.assertEqual(body.get("status"), "healthy")


if __name__ == "__main__":
    unittest.main()
