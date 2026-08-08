"""3×15s 独立成片初稿：脚本、混剪计划、批量渲染与审核。"""
from __future__ import annotations

import os
import re
from typing import Any

from services.video_mix import build_mix_plan, mix_enabled, render_mix_video

SLICE_SEGMENTS = [
    {"name": "钩子", "duration_sec": 3, "purpose": "3秒抓住注意力", "hint": "反问/结果/对比开场"},
    {"name": "痛点", "duration_sec": 6, "purpose": "共鸣用户场景"},
    {"name": "方案", "duration_sec": 6, "purpose": "给出解决步骤+CTA"},
]

HOOK_PREFIXES = {
    "痛点反问": "你是不是也在为{kw}发愁？",
    "结果先行": "很多人不知道，{prod}其实可以{kw}…",
    "对比冲击": "同样{kw}，为什么别人有效你却没变化？",
}


def slice_drafts_enabled() -> bool:
    return os.environ.get("SLICE_DRAFTS_ENABLED", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def slice_duration_sec() -> int:
    try:
        return max(10, min(30, int(os.environ.get("SLICE_DURATION_SEC", "15"))))
    except ValueError:
        return 15


def _scale_segments(total_sec: int) -> list[dict[str, Any]]:
    base = sum(int(s["duration_sec"]) for s in SLICE_SEGMENTS)
    ratio = total_sec / base if base else 1.0
    out = []
    for seg in SLICE_SEGMENTS:
        dur = max(2, int(round(float(seg["duration_sec"]) * ratio)))
        out.append({**seg, "duration_sec": dur})
    delta = total_sec - sum(s["duration_sec"] for s in out)
    if out and delta:
        out[-1]["duration_sec"] = max(2, out[-1]["duration_sec"] + delta)
    return out


def build_slice_script(
    *,
    base_script: str,
    variant: dict[str, Any],
    keyword: str,
    product_name: str,
    max_chars: int = 120,
) -> str:
    """为单条 15s 切片生成独立口播稿（痛点+解决方案结构）。"""
    hook_style = str(variant.get("hook_style") or "痛点反问")
    prod = product_name or keyword or "主推产品"
    kw = keyword or prod

    prefix_tpl = HOOK_PREFIXES.get(hook_style) or HOOK_PREFIXES["痛点反问"]
    prefix = prefix_tpl.format(kw=kw, prod=prod)

    body_src = re.sub(r"\s+", " ", (base_script or "")).strip()
    if len(body_src) > max_chars - len(prefix) - 10:
        body_src = body_src[: max_chars - len(prefix) - 10]

    pain = f"很多人{kw}踩坑，花冤枉钱还没效果。"
    solution = f"试试{prod}，痛点+解决方案一步到位。评论区告诉我你的情况。"
    if body_src and len(body_src) > 20:
        sentences = re.split(r"(?<=[。！？!?])", body_src)
        sentences = [s.strip() for s in sentences if s.strip()]
        if len(sentences) >= 2:
            pain = sentences[0][:40]
            solution = sentences[-1][:50] if len(sentences[-1]) > 8 else solution
        elif len(sentences) == 1:
            mid = len(sentences[0]) // 2
            pain = sentences[0][:mid][:40]
            solution = sentences[0][mid:][:50]

    script = f"{prefix}{pain}{solution}"
    brief = str(variant.get("angle") or variant.get("brief") or "")
    if brief and hook_style == "对比冲击" and len(script) < max_chars - 10:
        script = f"{script}（{brief[:20]}）"

    return script[:max_chars]


def build_slice_mix_plan(*, script: str, keyword: str, slice_id: str) -> dict[str, Any]:
    """15 秒切片专用混剪计划（痛点+解决方案）。"""
    segs = _scale_segments(slice_duration_sec())
    plan = build_mix_plan(script=script, breakdown_segments=segs, keyword=keyword)
    plan["slice_id"] = slice_id
    plan["structure"] = "痛点+解决方案"
    plan["duration_target_sec"] = slice_duration_sec()
    return plan


def generate_slice_drafts(
    *,
    base_script: str,
    keyword: str,
    strategy: dict[str, Any],
    product_name: str = "",
) -> dict[str, Any]:
    """基于 daily_directive 的 3 个 variant 生成独立脚本 + mix_plan。"""
    variants = list(strategy.get("variants") or [])
    daily = strategy.get("daily_directive") or {}
    if not variants and daily.get("slices"):
        variants = daily["slices"]
    if not variants:
        variants = [
            {"id": "S1", "hook_style": "痛点反问", "brief": keyword},
            {"id": "S2", "hook_style": "结果先行", "brief": keyword},
            {"id": "S3", "hook_style": "对比冲击", "brief": keyword},
        ]

    max_chars = int(os.environ.get("SLICE_SCRIPT_MAX_CHARS", "120"))
    drafts: list[dict[str, Any]] = []
    for v in variants[:3]:
        sid = str(v.get("id") or f"S{len(drafts)+1}")
        script = build_slice_script(
            base_script=base_script,
            variant=v,
            keyword=keyword,
            product_name=product_name or str((daily.get("primary_product") or {}).get("name") or ""),
            max_chars=max_chars,
        )
        mix_plan = build_slice_mix_plan(script=script, keyword=keyword, slice_id=sid)
        try:
            from services.bgm import pick_bgm_for_mix

            mix_plan["bgm"] = pick_bgm_for_mix(keyword=keyword, mix_plan=mix_plan)
            mix_plan["keyword"] = keyword
        except Exception:
            pass
        drafts.append({
            "id": sid,
            "hook_style": v.get("hook_style"),
            "brief": v.get("brief") or v.get("angle"),
            "script": script,
            "mix_plan": mix_plan,
            "duration_sec": slice_duration_sec(),
            "structure": "痛点+解决方案",
        })

    return {
        "ok": True,
        "count": len(drafts),
        "drafts": drafts,
        "structure": "痛点+解决方案",
        "duration_sec": slice_duration_sec(),
    }


def render_slice_drafts(
    *,
    drafts: list[dict[str, Any]],
    source_video: str,
    run_id: str,
    keyword: str = "",
    provider: str = "",
    product_image: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """为每条切片初稿独立渲染成片（AI provider + ffmpeg 混剪 + 商品图）。"""
    if not drafts:
        return {"ok": False, "error": "empty_drafts"}
    if not source_video:
        return {"ok": False, "error": "missing_source_video"}

    renders: list[dict[str, Any]] = []
    for draft in drafts[:3]:
        sid = str(draft.get("id") or "S1")
        script = str(draft.get("script") or "")
        mix_plan = draft.get("mix_plan") or {}
        source = source_video
        gen_result = None

        pid = (provider or "template").strip().lower()
        if script and pid not in ("template", ""):
            try:
                from services.video_providers.router import produce_video

                gen_result = produce_video(
                    provider=pid,
                    script=script,
                    run_id=f"{run_id}_{sid}",
                    source_video=source_video,
                    image_path=product_image,
                    extra={**(extra or {}), "slice_id": sid},
                )
                if gen_result.get("ok") and gen_result.get("output_path"):
                    source = str(gen_result["output_path"])
            except Exception as exc:
                gen_result = {"ok": False, "error": str(exc)}

        render: dict[str, Any] = {"ok": False, "error": "mix_disabled"}
        if mix_enabled() and mix_plan.get("timeline"):
            render = render_mix_video(
                mix_plan=mix_plan,
                source_video=source,
                run_id=f"{run_id}_{sid}",
                output_name=f"slice_{run_id[:6]}_{sid}",
                script=script,
                keyword=keyword,
                variant=sid,
                product_image=product_image,
            )
        elif gen_result and gen_result.get("ok"):
            render = {"ok": True, "output_path": source, "mode": "provider_only"}

        product_result = None
        out_path = str((render or {}).get("output_path") or "")
        if product_image and out_path and not str(render.get("product_compose")):
            try:
                from pathlib import Path

                from services.product_compose import attach_product_image

                product_result = attach_product_image(Path(out_path), product_image)
                if product_result.get("ok"):
                    out_path = str(product_result["output_path"])
                    render["output_path"] = out_path
                    render["product_compose"] = product_result
            except Exception:
                pass

        renders.append({
            "id": sid,
            "hook_style": draft.get("hook_style"),
            "script": script,
            "video_gen": gen_result,
            "render": render,
            "output_path": out_path if render.get("ok") else "",
        })

    ok_items = [r for r in renders if r.get("output_path")]
    recommended = ok_items[0]["id"] if ok_items else ""
    return {
        "ok": bool(ok_items),
        "count": len(ok_items),
        "renders": renders,
        "recommended": recommended,
        "recommended_path": ok_items[0]["output_path"] if ok_items else "",
    }


def submit_slice_drafts_for_review(
    *,
    run_id: str,
    renders: list[dict[str, Any]],
    title: str = "",
    payload: dict[str, Any] | None = None,
    notify_feishu: bool = True,
) -> dict[str, Any]:
    """将 3 条切片初稿批量提交审核队列。"""
    from services.review_queue import submit_batch_for_review

    items = []
    for r in renders:
        path = str(r.get("output_path") or "")
        if not path:
            continue
        items.append({
            "video_path": path,
            "script": str(r.get("script") or ""),
            "title": f"{title}·{r.get('id')}"[:40],
            "hook_style": r.get("hook_style"),
            "slice_id": r.get("id"),
            "payload": {
                **(payload or {}),
                "slice_id": r.get("id"),
                "hook_style": r.get("hook_style"),
                "batch": "slice_drafts",
            },
        })
    return submit_batch_for_review(
        run_id=run_id,
        items=items,
        notify_feishu=notify_feishu,
    )
