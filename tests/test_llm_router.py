"""LLM 多模型轮换网关测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


class LlmRouterTest(unittest.TestCase):
    def test_list_profiles_from_models_env(self) -> None:
        from services.llm_router import list_llm_profiles

        with patch.dict(
            "os.environ",
            {
                "LLM_API_BASE": "https://api.example.com/v1",
                "LLM_API_KEY": "sk-test",
                "LLM_MODELS": "model-a,model-b",
            },
        ):
            profiles = list_llm_profiles()
        self.assertEqual(len(profiles), 2)
        self.assertEqual(profiles[0]["model"], "model-a")

    def test_fallback_on_first_failure(self) -> None:
        from services.llm_router import chat_completion

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {"choices": [{"message": {"content": "hello"}}]}

        fail_resp = MagicMock()
        fail_resp.status_code = 429
        fail_resp.text = "rate limit"

        with patch.dict(
            "os.environ",
            {
                "LLM_API_BASE": "https://api.example.com/v1",
                "LLM_API_KEY": "sk-test",
                "LLM_MODELS": "bad-model,good-model",
                "LLM_ROTATION_ENABLED": "1",
            },
        ):
            with patch("services.llm_router.requests.post", side_effect=[fail_resp, ok_resp]) as mock_post:
                out = chat_completion(messages=[{"role": "user", "content": "hi"}])
        self.assertTrue(out.get("success"))
        self.assertEqual(out.get("model_used"), "good-model")
        self.assertEqual(mock_post.call_count, 2)

    def test_engineering_llm_api(self) -> None:
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app)
        r = client.get("/api/engineering/llm")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("ok") is not False)


if __name__ == "__main__":
    unittest.main()
