"""LLM 多模型轮换网关 — 按序尝试主模型与备选模型，降低单点封禁风险。"""
from __future__ import annotations

import json
import os
from typing import Any

import requests


def rotation_enabled() -> bool:
    return os.environ.get("LLM_ROTATION_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def _split_models(raw: str) -> list[str]:
    out: list[str] = []
    for part in (raw or "").replace(";", ",").split(","):
        name = part.strip()
        if name and name not in out:
            out.append(name)
    return out


def list_llm_profiles() -> list[dict[str, str]]:
    """返回待尝试的 LLM 配置列表（base / key / model）。"""
    default_base = (os.environ.get("LLM_API_BASE") or os.environ.get("OPENAI_BASE_URL") or "").strip().rstrip("/")
    default_key = (os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    default_model = (os.environ.get("LLM_MODEL") or "deepseek-chat").strip()

    profiles: list[dict[str, str]] = []

    # 高级：JSON 数组，每项可独立 base/key/model
    raw_json = (os.environ.get("LLM_PROFILES_JSON") or "").strip()
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, list):
                for row in parsed:
                    if not isinstance(row, dict):
                        continue
                    base = str(row.get("base") or row.get("api_base") or default_base).strip().rstrip("/")
                    key = str(row.get("key") or row.get("api_key") or default_key).strip()
                    model = str(row.get("model") or default_model).strip()
                    if base and key and model:
                        profiles.append({"base": base, "key": key, "model": model, "label": str(row.get("label") or model)})
        except Exception:
            pass

    if profiles:
        return profiles

    models = _split_models(os.environ.get("LLM_MODELS") or "")
    if not models:
        primary = default_model
        fallbacks = _split_models(os.environ.get("LLM_FALLBACK_MODELS") or "")
        models = [primary] + [m for m in fallbacks if m != primary]

    for model in models:
        if default_base and default_key and model:
            profiles.append({"base": default_base, "key": default_key, "model": model, "label": model})

    return profiles


def llm_router_status() -> dict[str, Any]:
    profiles = list_llm_profiles()
    return {
        "ok": True,
        "rotation_enabled": rotation_enabled(),
        "profile_count": len(profiles),
        "models": [p.get("model") for p in profiles],
        "configured": len(profiles) > 0 and bool(profiles[0].get("base") and profiles[0].get("key")),
    }


def chat_completion(
    *,
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    timeout_sec: int | None = None,
) -> dict[str, Any]:
    """OpenAI 兼容 chat/completions，支持多模型轮换。"""
    profiles = list_llm_profiles()
    if not profiles:
        return {"success": False, "error": "llm_not_configured"}

    timeout = timeout_sec or int(os.environ.get("LLM_TIMEOUT_SEC", "60") or 60)
    errors: list[dict[str, str]] = []
    candidates = profiles if rotation_enabled() else profiles[:1]

    for idx, prof in enumerate(candidates):
        base = prof["base"]
        key = prof["key"]
        model = prof["model"]
        try:
            resp = requests.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "temperature": temperature},
                timeout=timeout,
            )
            if resp.status_code >= 400:
                errors.append({"model": model, "error": resp.text[:200], "status": str(resp.status_code)})
                continue
            data = resp.json()
            text = str(data["choices"][0]["message"]["content"] or "").strip()
            return {
                "success": True,
                "text": text,
                "model_used": model,
                "profile_index": idx,
                "attempts": idx + 1,
            }
        except Exception as exc:
            errors.append({"model": model, "error": str(exc)[:200]})
            continue

    return {
        "success": False,
        "error": "llm_all_profiles_failed",
        "attempts": len(candidates),
        "errors": errors,
    }


def chat_prompt(prompt: str, *, temperature: float = 0.7) -> dict[str, Any]:
    return chat_completion(messages=[{"role": "user", "content": prompt}], temperature=temperature)
