"""从竞品/热榜提取黄金3秒话术与 BGM，写入知识库。"""
from __future__ import annotations

import json
import os
from typing import Any

import bootstrap
from core.storage import kb_upsert, save_episodic


def insights_enabled() -> bool:
    return os.environ.get("PERCEPTION_INSIGHTS_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def extract_golden_hook(*, title: str = "", transcript: str = "", asr_text: str = "") -> str:
    """提取约 3 秒口播量的黄金开场话术。"""
    source = (asr_text or transcript or title or "").strip()
    if not source:
        return ""
    sentences = [s.strip() for s in source.replace("\n", "。").split("。") if s.strip()]
    if sentences:
        hook = sentences[0]
        if len(hook) > 48:
            hook = hook[:48]
        return hook
    return source[:36]


def pick_viral_bgm(*, keyword: str = "") -> dict[str, Any]:
    path = bootstrap.project_root() / "data" / "bgm_library.json"
    pool: list[dict[str, Any]] = []
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                pool = [x for x in raw if isinstance(x, dict)]
        except Exception:
            pool = []
    if not pool:
        pool = [
            {"name": "卡点鼓点-护肤", "mood": "energetic", "bpm": 128, "tags": "护肤,口播"},
            {"name": "温柔钢琴-种草", "mood": "soft", "bpm": 90, "tags": "面膜,种草"},
            {"name": "悬疑开场-痛点", "mood": "suspense", "bpm": 110, "tags": "痛点,转化"},
        ]
    key = (keyword or "").lower()
    for item in pool:
        tags = str(item.get("tags") or "").lower()
        if key and key in tags:
            return dict(item)
    return dict(pool[0])


def ingest_competitor_insights(
    *,
    competitors: list[dict[str, Any]],
    run_id: str = "perception-scan",
    keyword: str = "",
) -> dict[str, Any]:
    """将黄金3秒话术 + BGM 推荐写入 hotspot 库。"""
    if not insights_enabled():
        return {"ok": False, "reason": "insights_disabled"}

    hooks: list[dict[str, Any]] = []
    bgm = pick_viral_bgm(keyword=keyword)
    bgm_id = kb_upsert(
        library="hotspot",
        title=f"BGM·{bgm.get('name', '推荐')}",
        body=json.dumps(bgm, ensure_ascii=False),
        tags=f"bgm,auto_ingest,{keyword}",
        platform="douyin",
    )

    for c in competitors[:5]:
        hook = extract_golden_hook(
            title=str(c.get("title") or ""),
            transcript=str(c.get("snippet") or ""),
            asr_text=str(c.get("asr_text") or ""),
        )
        if not hook:
            continue
        kid = kb_upsert(
            library="hotspot",
            title=f"黄金3秒·{hook[:20]}",
            body=hook,
            tags=f"golden_hook,auto_ingest,{keyword}",
            platform=str(c.get("platform") or "douyin"),
        )
        hooks.append({"kb_id": kid, "hook": hook, "url": c.get("url"), "like_rate": c.get("like_rate")})

    save_episodic(
        run_id=run_id,
        agent="data_perception",
        observation=f"感知洞察入库：{len(hooks)} 条黄金话术，BGM={bgm.get('name')}",
        action="ingest_perception_insights",
        payload={"hooks": hooks, "bgm_kb_id": bgm_id, "keyword": keyword},
    )
    return {"ok": True, "hooks_ingested": len(hooks), "bgm_kb_id": bgm_id, "bgm": bgm, "hooks": hooks}
