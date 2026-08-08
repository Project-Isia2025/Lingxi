"""违禁词库 — 广告法 + 平台规则。"""
from __future__ import annotations

import json
import re
from pathlib import Path

import bootstrap

_DATA_CANDIDATES = (
    Path(__file__).resolve().parent / "data" / "banned_words.json",
    bootstrap.project_root() / "memory" / "data" / "banned_words.json",
)


class BannedWordsFilter:
    def __init__(self) -> None:
        self.words = self._load_banned_words()
        self.patterns = [re.compile(re.escape(w), re.IGNORECASE) for w in self.words if w]

    def _load_banned_words(self) -> list[str]:
        for words_file in _DATA_CANDIDATES:
            if words_file.exists():
                raw = json.loads(words_file.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    return [str(w).strip() for w in raw if str(w).strip()]
                if isinstance(raw, dict):
                    out: list[str] = []
                    for group in raw.values():
                        if isinstance(group, list):
                            out.extend(str(w).strip() for w in group if str(w).strip())
                    return out
        try:
            from core.storage import load_forbidden_words

            rows = load_forbidden_words()
            return [str(r["word"]) for r in rows if r.get("word")]
        except Exception:
            return []

    def reload(self) -> None:
        self.words = self._load_banned_words()
        self.patterns = [re.compile(re.escape(w), re.IGNORECASE) for w in self.words if w]

    def check(self, text: str) -> list[str]:
        """返回命中的违禁词列表。"""
        hits = []
        for word, pattern in zip(self.words, self.patterns):
            if pattern.search(text):
                hits.append(word)
        return hits

    def sanitize(self, text: str) -> str:
        """将违禁词替换为星号。"""
        for word, pattern in zip(self.words, self.patterns):
            text = pattern.sub("*" * max(4, len(word)), text)
        return text

    def filter_metadata(self) -> dict:
        return {"count": len(self.words), "source": "memory/data/banned_words.json"}
