"""BGM 选择与路径解析。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import bootstrap


def bgm_enabled() -> bool:
    return os.environ.get("BGM_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def bgm_volume() -> float:
    try:
        return max(0.01, min(float(os.environ.get("BGM_VOLUME", "0.12")), 1.0))
    except ValueError:
        return 0.12


def load_bgm_library() -> list[dict[str, Any]]:
    path = bootstrap.project_root() / "data" / "bgm_library.json"
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
    except Exception:
        pass
    return []


def resolve_bgm_path(bgm: dict[str, Any]) -> str:
    rel = str(bgm.get("file") or "").strip()
    if not rel:
        return ""
    p = Path(rel)
    if not p.is_absolute():
        p = bootstrap.project_root() / rel
    return str(p.resolve()) if p.is_file() else ""


def pick_bgm_for_mix(*, keyword: str = "", mix_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    if mix_plan and mix_plan.get("bgm"):
        bgm = dict(mix_plan["bgm"])
        bgm["path"] = resolve_bgm_path(bgm)
        return bgm
    from services.perception_insights import pick_viral_bgm

    bgm = pick_viral_bgm(keyword=keyword)
    bgm["path"] = resolve_bgm_path(bgm)
    return bgm
