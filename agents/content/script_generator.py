"""LLM 脚本生成。"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from memory.banned_words import BannedWordsFilter
from memory.vector_store import VectorStore


class ScriptGenerator:
    def __init__(self) -> None:
        self.vector_store = VectorStore()
        self.banned_filter = BannedWordsFilter()
        self.llm = None
        self.prompt = None
        api_key = (os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
        api_base = (os.environ.get("LLM_API_BASE") or os.environ.get("OPENAI_BASE_URL") or "").strip()
        model = (os.environ.get("LLM_MODEL") or "deepseek-chat").strip()
        if api_key:
            try:
                from langchain_core.prompts import ChatPromptTemplate
                from langchain_openai import ChatOpenAI

                kwargs: dict[str, Any] = {"model": model, "temperature": 0.7, "api_key": api_key}
                if api_base:
                    kwargs["base_url"] = api_base
                self.llm = ChatOpenAI(**kwargs)
                self.prompt = ChatPromptTemplate.from_messages(
                    [
                        (
                            "system",
                            """你是一个专业短视频带货脚本编剧。
根据商品信息和参考爆款脚本，创作一条 30-60 秒的短视频脚本。
要求：开头 3 秒 hook、场景化卖点、明确 CTA、口语化、避免违禁词。
参考爆款脚本特征：{reference_features}""",
                        ),
                        (
                            "human",
                            "商品信息：{product_info}\n目标人群：{target_audience}\n"
                            "卖点：{selling_points}\n期望风格：{style}",
                        ),
                    ]
                )
            except Exception:
                pass

    async def generate(self, product: dict, style: str = "激情带货") -> dict:
        references = await self.vector_store.search(
            "scripts",
            query=f"{product.get('name', '')} {style}",
            limit=3,
        )

        if self.llm and self.prompt:
            chain = self.prompt | self.llm
            response = await chain.ainvoke(
                {
                    "reference_features": self._extract_features(references),
                    "product_info": json.dumps(product, ensure_ascii=False),
                    "target_audience": product.get("target_audience", "通用"),
                    "selling_points": ", ".join(product.get("selling_points", [])),
                    "style": style,
                }
            )
            script = response.content
        else:
            script = self._template_script(product, style)

        banned_hits = self.banned_filter.check(script)
        if banned_hits:
            script = self.banned_filter.sanitize(script)

        parsed = self._parse_script(script)
        return {
            "raw_script": script,
            "parsed": parsed,
            "banned_words_hit": banned_hits,
            "estimated_duration": self._estimate_duration(script),
        }

    def _template_script(self, product: dict, style: str) -> str:
        name = product.get("name") or "好物"
        return (
            f"【Hook】你还在为{name}发愁吗？\n"
            f"【卖点】这款{name}真的绝了，{style}风格实测有效！\n"
            f"【CTA】点击下方链接，限时优惠别错过！"
        )

    def _extract_features(self, references: list) -> str:
        parts = []
        for r in references:
            if isinstance(r, dict):
                text = str(r.get("text") or r.get("title") or "")[:200]
            else:
                payload = getattr(r, "payload", None) or {}
                text = str(payload.get("text") or "")[:200]
            if text:
                parts.append(text)
        return "\n".join(parts) or "强 hook + 场景化 + CTA"

    def _parse_script(self, script: str) -> dict:
        segments = []
        for line in script.split("\n"):
            line = line.strip()
            if not line:
                continue
            m = re.match(r"【(.+?)】(.+)", line)
            if m:
                segments.append({"label": m.group(1), "voiceover": m.group(2).strip()})
            else:
                segments.append({"label": "段", "voiceover": line})
        return {"segments": segments, "subtitles": [s["voiceover"] for s in segments]}

    def _estimate_duration(self, script: str) -> int:
        char_count = len(script.replace(" ", "").replace("\n", ""))
        return max(1, char_count // 4)
