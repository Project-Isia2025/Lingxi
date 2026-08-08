"""内容生成：双 Agent 改写、风控、去重、混剪计划、多渠道文案。"""
from __future__ import annotations

import hashlib
import os
import re
from typing import Any

import requests

from services.dedup import check_duplicate, record_script
from services.video_mix import build_mix_plan


def _dedupe_key(text: str) -> str:
    norm = re.sub(r"\s+", "", (text or "").strip().lower())
    return hashlib.sha256(norm.encode()).hexdigest()[:16]


def check_text_risk(text: str, forbidden_rows: list[dict[str, Any]]) -> dict[str, Any]:
    raw = str(text or "")
    hits = []
    replaced = raw
    for row in forbidden_rows:
        w = str(row.get("word") or "").strip()
        if not w or w not in raw:
            continue
        rep = str(row.get("replace_word") or "").strip()
        hits.append({"word": w, "type": row.get("word_type"), "replace": rep})
        if rep:
            replaced = replaced.replace(w, rep)
    forbidden_n = sum(1 for h in hits if h.get("type") == "forbidden")
    return {
        "passed": forbidden_n == 0,
        "hits": hits,
        "replaced_text": replaced,
        "forbidden_count": forbidden_n,
        "drain_count": sum(1 for h in hits if h.get("type") == "drain"),
        "summary": "通过" if forbidden_n == 0 else f"违禁词 {forbidden_n} 处",
    }


def _forbidden_prompt_block(forbidden_rows: list[dict[str, Any]]) -> str:
    words = [str(r.get("word") or "") for r in forbidden_rows if r.get("word")]
    if not words:
        return ""
    return "严禁使用以下词：" + "、".join(words[:30])


def collect_ocr_context(perception: dict[str, Any] | None) -> str:
    """从感知结果聚合 OCR/正文深度内容，供 LLM 改写。"""
    if os.environ.get("CONTENT_OCR_INJECT", "1").strip().lower() in ("0", "false", "no"):
        return ""
    parts: list[str] = []
    for comp in (perception or {}).get("competitors") or []:
        if not isinstance(comp, dict):
            continue
        ocr = str(comp.get("ocr_text") or "").strip()
        asr = str(comp.get("asr_text") or "").strip()
        body = str(comp.get("body") or comp.get("snippet") or "").strip()
        title = str(comp.get("title") or "").strip()
        if asr:
            parts.append(f"【竞品ASR·{title[:20]}】\n{asr[:600]}")
        elif ocr:
            parts.append(f"【竞品OCR·{title[:20]}】\n{ocr[:600]}")
        elif body and len(body) > 60:
            parts.append(f"【竞品正文·{title[:20]}】\n{body[:600]}")
    for bd in (perception or {}).get("breakdowns") or []:
        if not isinstance(bd, dict):
            continue
        ocr = str(bd.get("ocr_text") or "").strip()
        asr = str(bd.get("asr_text") or "").strip()
        transcript = str(bd.get("original_transcript") or "").strip()
        if asr:
            parts.append(f"【参考ASR】\n{asr[:800]}")
        elif ocr:
            parts.append(f"【参考OCR】\n{ocr[:800]}")
        elif transcript and len(transcript) > 80 and bd.get("platform") == "xiaohongshu":
            parts.append(f"【参考笔记】\n{transcript[:800]}")
    if not parts:
        return ""
    return "以下 OCR/ASR/竞品正文可作为改写依据（勿照搬违禁表述）：\n" + "\n\n".join(parts[:4])


def _ocr_prompt_block(ocr_context: str) -> str:
    if not ocr_context.strip():
        return ""
    return f"\n{ocr_context[:2500]}\n"


def _llm_call(prompt: str) -> dict[str, Any]:
    from services.llm_router import chat_prompt

    out = chat_prompt(prompt, temperature=0.7)
    if out.get("success"):
        return {"success": True, "text": out.get("text"), "model_used": out.get("model_used")}
    if out.get("error") == "llm_not_configured":
        return {"success": False, "error": "llm_not_configured"}
    return {"success": False, "error": out.get("error") or "llm_failed", "errors": out.get("errors")}


def _dual_agent_rewrite(source: str, *, style: str, max_chars: int, forbidden_block: str, ocr_block: str = "") -> dict[str, Any]:
    """总结 Agent → 润色 Agent 两阶段改写。"""
    summary_prompt = f"""你是内容总结Agent。提取以下素材的核心卖点与结构要点，200字以内。
{forbidden_block}{ocr_block}

素材：
{source[:2000]}
"""
    summary = _llm_call(summary_prompt)
    if not summary.get("success"):
        return {"success": False, "error": summary.get("error"), "degraded": True}

    polish_prompt = f"""你是口播润色Agent。将要点改写为{style}风格短视频口播稿。
要求：{max_chars}字以内；口语化；开头3秒有钩子；不要编造事实；可参考 OCR 中的真实表述但不要抄袭。
{forbidden_block}

要点：
{summary.get('text', '')[:800]}
"""
    polish = _llm_call(polish_prompt)
    if not polish.get("success"):
        return {"success": False, "error": polish.get("error"), "degraded": True, "summary": summary.get("text")}

    script = str(polish.get("text") or "")[:max_chars]
    return {
        "success": True,
        "script": script,
        "model_used": polish.get("model_used"),
        "degraded": False,
        "pipeline": "dual_agent",
        "summary": summary.get("text", "")[:200],
    }


def _llm_rewrite(source: str, *, style: str, max_chars: int, forbidden_block: str = "", ocr_block: str = "") -> dict[str, Any]:
    if os.environ.get("CONTENT_DUAL_AGENT", "1").strip().lower() not in ("0", "false", "no"):
        dual = _dual_agent_rewrite(source, style=style, max_chars=max_chars, forbidden_block=forbidden_block, ocr_block=ocr_block)
        if dual.get("success"):
            return dual
    from services.llm_router import chat_prompt

    prompt = f"""你是口播内容Agent。将以下素材改写为{style}风格短视频口播稿。
要求：{max_chars}字以内；口语化；有钩子；不要编造事实；可参考 OCR 竞品正文。
{forbidden_block}{ocr_block}

素材：
{source[:2000]}
"""
    out = chat_prompt(prompt, temperature=0.7)
    if not out.get("success"):
        return {"success": False, "error": out.get("error"), "degraded": True, "errors": out.get("errors")}
    script = str(out.get("text") or "")[:max_chars]
    return {
        "success": True,
        "script": script,
        "model_used": out.get("model_used"),
        "degraded": False,
        "pipeline": "single",
    }


def _template_rewrite(source: str, *, max_chars: int, angle: str, keyword: str) -> dict[str, Any]:
    hook = f"你是不是也在为{keyword}发愁？"
    body = source.replace("\n", " ")[: max_chars - 80]
    script = f"{hook}今天分享3个关键点。{body}… 如果你也想要系统方案，评论区告诉我。"
    return {
        "success": True,
        "script": script[:max_chars],
        "model_used": "template",
        "degraded": True,
        "pipeline": "template",
        "summary": [hook, angle[:40]],
    }


def attach_breakdown_segments(script: str, segments: list[dict]) -> list[dict]:
    if not segments:
        return []
    out = []
    for seg in segments[:5]:
        out.append(
            {
                "name": seg.get("name"),
                "hint": seg.get("hint"),
                "script_excerpt": script[:80],
            }
        )
    return out


def _build_variants(base_script: str, strategy: dict[str, Any], max_chars: int) -> list[dict[str, str]]:
    variants = []
    for v in (strategy.get("variants") or [])[:3]:
        hook = v.get("hook_style") or "痛点"
        text = base_script
        if hook == "结果先行" and len(text) > 40:
            text = f"很多人不知道，{text[20:]}"
        elif hook == "对比冲击" and len(text) > 30:
            text = f"同样的问题，不同结果：{text[15:]}"
        variants.append({"id": v.get("id") or "A", "hook_style": hook, "script": text[:max_chars]})
    return variants


def generate_content(
    *,
    source: str,
    keyword: str,
    angle: str,
    memory: dict[str, Any],
    strategy: dict[str, Any],
    run_id: str = "",
    platform: str = "douyin",
    perception: dict[str, Any] | None = None,
) -> dict[str, Any]:
    style = os.environ.get("CONTENT_STYLE", "爆款口播")
    max_chars = int(os.environ.get("CONTENT_MAX_CHARS", "300"))
    forbidden_rows = memory.get("forbidden_rows") or []
    forbidden_block = _forbidden_prompt_block(forbidden_rows)
    ocr_context = collect_ocr_context(perception)
    ocr_block = _ocr_prompt_block(ocr_context)
    if ocr_context:
        source = f"{source}\n\n{ocr_context[:2000]}"

    rewrite = _llm_rewrite(source, style=style, max_chars=max_chars, forbidden_block=forbidden_block, ocr_block=ocr_block)
    if not rewrite.get("success"):
        rewrite = _template_rewrite(source, max_chars=max_chars, angle=angle, keyword=keyword)

    script = str(rewrite.get("script") or "").strip()
    risk = check_text_risk(script, forbidden_rows)
    final_script = str(risk.get("replaced_text") or script)

    dup = check_duplicate(final_script, run_id=run_id)

    from services.strategy import render_channel_preview

    geo = memory.get("geo") or {}
    channels = render_channel_preview(final_script, geo)

    viral = memory.get("viral_structure") or []
    segs = viral[0].get("segments") if viral else []
    breakdown_segments = attach_breakdown_segments(final_script, segs or [])
    mix_plan = build_mix_plan(script=final_script, breakdown_segments=segs or None, keyword=keyword)
    try:
        from services.bgm import pick_bgm_for_mix

        mix_plan["bgm"] = pick_bgm_for_mix(keyword=keyword, mix_plan=mix_plan)
        mix_plan["keyword"] = keyword
    except Exception:
        pass
    variants = _build_variants(final_script, strategy, max_chars)

    slice_drafts: dict[str, Any] = {}
    if os.environ.get("SLICE_DRAFTS_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off"):
        try:
            from services.slice_drafts import generate_slice_drafts

            inv_prod = strategy.get("inventory_product") or {}
            slice_drafts = generate_slice_drafts(
                base_script=final_script,
                keyword=keyword,
                strategy=strategy,
                product_name=str(inv_prod.get("name") or keyword),
            )
        except Exception as exc:
            slice_drafts = {"ok": False, "error": str(exc)[:200]}

    if not dup.get("duplicate"):
        record_script(final_script, run_id=run_id, keyword=keyword, platform=platform)

    tts_variants: dict[str, Any] = {}
    if os.environ.get("TTS_AB_ENABLED", "1").strip().lower() not in ("0", "false", "no"):
        try:
            from services.tts import ab_enabled, synthesize_ab_variants

            if ab_enabled():
                tts_variants = synthesize_ab_variants(final_script, run_id=run_id)
        except Exception:
            tts_variants = {"ok": False}

    return {
        "source_excerpt": source[:500],
        "rewrite": rewrite,
        "script": final_script,
        "dedupe_hash": dup.get("dedupe_hash") or _dedupe_key(final_script),
        "dedupe_duplicate": dup.get("duplicate"),
        "dedupe_info": dup,
        "breakdown_segments": breakdown_segments,
        "mix_plan": mix_plan,
        "variants": variants,
        "slice_drafts": slice_drafts,
        "tts_variants": tts_variants,
        "ocr_context_used": bool(ocr_context),
        "ocr_excerpt": ocr_context[:300] if ocr_context else "",
        "channel_contents": channels,
        "risk_check": {
            "passed": risk.get("passed"),
            "summary": risk.get("summary"),
            "forbidden_count": risk.get("forbidden_count"),
            "drain_count": risk.get("drain_count"),
        },
        "degraded": bool(rewrite.get("degraded")) or not risk.get("passed"),
    }
