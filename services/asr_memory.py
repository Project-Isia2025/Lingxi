"""ASR 转写结果写入知识库与 episodic 记忆。"""
from __future__ import annotations

import os
from typing import Any

from core.storage import kb_upsert, save_episodic


def asr_memory_enabled() -> bool:
    return os.environ.get("ASR_MEMORY_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def ingest_asr_transcript(
    *,
    text: str,
    title: str = "",
    platform: str = "xiaohongshu",
    note_id: str = "",
    source_url: str = "",
    run_id: str = "",
    keyword: str = "",
) -> dict[str, Any]:
    """将 ASR 文本写入 hotspot 知识库并记录 episodic。"""
    body = str(text or "").strip()
    if not body:
        return {"ok": False, "reason": "empty_text"}
    if not asr_memory_enabled():
        return {"ok": False, "reason": "asr_memory_disabled"}

    label = (title or note_id or "笔记")[:60]
    tags = ",".join(filter(None, ["asr", "auto_ingest", keyword.strip(), note_id[:24]]))
    item_id = kb_upsert(
        library="hotspot",
        title=f"ASR·{label}",
        body=body[:4000],
        tags=tags,
        platform=platform,
    )
    rid = run_id or f"asr-{note_id or 'anon'}"
    save_episodic(
        run_id=rid,
        agent="memory",
        observation=f"ASR 转写入库：{label}",
        action="kb_upsert_asr",
        payload={
            "kb_id": item_id,
            "note_id": note_id,
            "source_url": source_url,
            "platform": platform,
            "text_len": len(body),
        },
    )
    try:
        from services.dashboard_hub import notify_dashboard_update

        notify_dashboard_update(reason="asr_ingest")
    except Exception:
        pass
    return {"ok": True, "kb_id": item_id, "run_id": rid}
    """从竞品/笔记详情 dict 中提取 ASR 并入库。"""
    text = str(comp.get("asr_text") or "").strip()
    if not text:
        return {"ok": False, "reason": "no_asr_text"}
    return ingest_asr_transcript(
        text=text,
        title=str(comp.get("title") or ""),
        platform=str(comp.get("platform") or "xiaohongshu"),
        note_id=str(comp.get("note_id") or comp.get("video_id") or ""),
        source_url=str(comp.get("url") or ""),
        run_id=run_id,
        keyword=keyword,
    )


def ingest_ocr_text(
    *,
    text: str,
    title: str = "",
    platform: str = "xiaohongshu",
    note_id: str = "",
    source_url: str = "",
    run_id: str = "",
    keyword: str = "",
) -> dict[str, Any]:
    """将 OCR 文本写入 hotspot 知识库。"""
    body = str(text or "").strip()
    if not body:
        return {"ok": False, "reason": "empty_text"}
    if not asr_memory_enabled():
        return {"ok": False, "reason": "ocr_memory_disabled"}

    label = (title or note_id or "笔记")[:60]
    tags = ",".join(filter(None, ["ocr", "auto_ingest", keyword.strip(), note_id[:24]]))
    item_id = kb_upsert(
        library="hotspot",
        title=f"OCR·{label}",
        body=body[:4000],
        tags=tags,
        platform=platform,
    )
    rid = run_id or f"ocr-{note_id or 'anon'}"
    save_episodic(
        run_id=rid,
        agent="memory",
        observation=f"OCR 识别入库：{label}",
        action="kb_upsert_ocr",
        payload={"kb_id": item_id, "note_id": note_id, "source_url": source_url, "text_len": len(body)},
    )
    try:
        from services.dashboard_hub import notify_dashboard_update

        notify_dashboard_update(reason="ocr_ingest")
    except Exception:
        pass
    return {"ok": True, "kb_id": item_id, "run_id": rid}
