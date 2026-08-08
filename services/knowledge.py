"""记忆库：RAG 检索、品牌配置、违禁词、爆款结构。"""
from __future__ import annotations

from typing import Any

from core.storage import kb_search, kb_upsert, load_brand_config, load_forbidden_words, save_episodic, seed_kb_if_empty


def build_material_context(bundle: dict[str, Any]) -> str:
    lines: list[str] = []
    for lib, hits in (bundle.get("items") or {}).items():
        if not hits:
            continue
        lines.append(f"## {lib}")
        for h in hits:
            title = (h.get("title") or "").strip()
            body = (h.get("body") or "").strip()[:500]
            lines.append(f"- {title}\n  {body}")
    return "\n".join(lines).strip()


def retrieve_memory(
    *,
    query: str,
    title: str = "",
    platform: str = "douyin",
    perception: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seed_kb_if_empty()
    q = f"{title} {query}".strip()
    items: dict[str, list] = {}
    for lib in ("story", "faq", "hotspot", "sales_script", "sop"):
        items[lib] = kb_search(query=q, library=lib, limit=3)

    brand = load_brand_config()
    forbidden = load_forbidden_words()
    brand_words = [str(w) for w in (brand.get("forbidden_words") or []) if str(w).strip()]

    sop_entries = []
    for lib, hits in items.items():
        for h in hits:
            sop_entries.append(
                {
                    "library": lib,
                    "title": h.get("title"),
                    "body_excerpt": str(h.get("body") or "")[:400],
                }
            )

    viral_structure = []
    for bd in (perception or {}).get("breakdowns") or []:
        segs = bd.get("breakdown_segments") or []
        if segs:
            viral_structure.append({"url": bd.get("url"), "segments": segs[:8]})

    top_kb = sorted(
        [h for hits in items.values() for h in hits],
        key=lambda x: float(x.get("roi_score") or 0),
        reverse=True,
    )[:5]

    return {
        "query": query,
        "platform": platform,
        "material_bundle": {"items": items},
        "material_context": build_material_context({"items": items}),
        "forbidden_words": brand_words + [r["word"] for r in forbidden if r.get("word_type") == "forbidden"],
        "forbidden_rows": forbidden,
        "sop_entries": sop_entries[:12],
        "geo": {
            "brand_name": brand.get("brand_name") or "",
            "cta_text": brand.get("cta_text") or "",
            "industry": brand.get("industry") or "",
        },
        "top_kb_items": top_kb,
        "viral_structure": viral_structure,
    }


def ingest_content_feedback(
    *,
    run_id: str,
    script: str,
    keyword: str,
    platform: str,
    published: bool = False,
) -> dict[str, Any]:
    """发布成功后回写热点库与 episodic 记忆。"""
    if not script.strip():
        return {"ok": False, "reason": "empty_script"}
    item_id = kb_upsert(
        library="hotspot",
        title=f"{keyword}口播稿",
        body=script[:2000],
        tags=f"{keyword},auto_ingest",
        platform=platform,
    )
    save_episodic(
        run_id=run_id,
        agent="memory",
        observation=f"内容已{'发布' if published else '生成'}",
        action="kb_upsert_hotspot",
        payload={"kb_id": item_id, "keyword": keyword},
    )
    return {"ok": True, "kb_id": item_id}


def save_agent_episode(*, run_id: str, agent: str, observation: str, action: str, payload: dict | None = None) -> None:
    save_episodic(run_id=run_id, agent=agent, observation=observation, action=action, payload=payload)
