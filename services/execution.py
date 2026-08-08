"""执行：发布计划、自动发布、投流调优、质检、任务队列。"""
from __future__ import annotations

import uuid
from typing import Any

from core.storage import metrics_record, save_execution_job
from services.ad_optimizer import build_ad_plan, deploy_ad_plan
from services.video_mix import mix_enabled, render_ab_mix_videos, render_mix_video


def _maybe_render_slice_drafts(
    *,
    run_id: str,
    goal: Any,
    content: dict[str, Any],
    video_path: str,
    strategy: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """渲染 3×15s 独立切片初稿。"""
    slice_pack = content.get("slice_drafts") or {}
    if not slice_pack.get("ok") or not (slice_pack.get("drafts") or []):
        return None

    extra = getattr(goal, "extra", {}) or {}
    source = str(extra.get("source_video") or video_path or "").strip()
    if not source:
        return None

    try:
        from services.product_compose import resolve_product_image
        from services.slice_drafts import render_slice_drafts

        inv_prod = (strategy or {}).get("inventory_product") or {}
        product_image = resolve_product_image(extra=extra, inventory_product=inv_prod)
        provider = str(
            (strategy or {}).get("selected_provider")
            or getattr(goal, "video_provider", "")
            or extra.get("video_provider")
            or "template"
        ).strip().lower()

        return render_slice_drafts(
            drafts=list(slice_pack.get("drafts") or []),
            source_video=source,
            run_id=run_id,
            keyword=str((strategy or {}).get("primary_keyword") or getattr(goal, "keyword", "") or ""),
            provider=provider,
            product_image=product_image,
            extra=extra,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


def _maybe_render_video(
    *,
    run_id: str,
    goal: Any,
    content: dict[str, Any],
    video_path: str,
    strategy: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """若启用混剪且存在 mix_plan，用 AI provider 或 ffmpeg 渲染成片。"""
    mix_plan = content.get("mix_plan") or {}
    extra = getattr(goal, "extra", {}) or {}
    source = str(extra.get("source_video") or video_path or "").strip()
    script = str(content.get("script") or "")
    provider = str(
        (strategy or {}).get("selected_provider")
        or getattr(goal, "video_provider", "")
        or extra.get("video_provider")
        or "template"
    ).strip().lower()

    gen_result = None
    if source or script:
        try:
            from services.video_providers.router import produce_video

            gen_result = produce_video(
                provider=provider,
                script=script,
                run_id=run_id,
                source_video=source,
                image_path=str(extra.get("product_image") or ""),
                extra=extra,
            )
            if gen_result.get("ok") and gen_result.get("output_path"):
                source = str(gen_result["output_path"])
        except Exception as exc:
            gen_result = {"ok": False, "error": str(exc)}

    if not mix_enabled() or not mix_plan.get("timeline") or not source:
        if gen_result and gen_result.get("ok"):
            return source, {"video_gen": gen_result}
        return video_path, gen_result

    tts_ab = content.get("tts_variants") or {}
    if bool(extra.get("tts_ab_render", True)) and tts_ab.get("ok") and (tts_ab.get("variants") or []):
        ab_render = render_ab_mix_videos(
            mix_plan=mix_plan,
            source_video=source,
            script=script,
            tts_variants=tts_ab,
            run_id=run_id,
        )
        if ab_render.get("ok"):
            rec = str(ab_render.get("recommended") or "A")
            picked = next((v for v in ab_render.get("variants") or [] if v.get("variant") == rec), None)
            path = ((picked or {}).get("render") or {}).get("output_path")
            if path:
                return str(path), {"mode": "ab", **ab_render}

    voice = str(extra.get("tts_voice") or "")
    render = render_mix_video(
        mix_plan=mix_plan,
        source_video=source,
        run_id=run_id,
        output_name=str(extra.get("mix_output_name") or ""),
        script=script,
        enable_tts=bool(extra.get("enable_tts", True)),
        voice=voice,
        keyword=str((strategy or {}).get("primary_keyword") or getattr(goal, "keyword", "") or ""),
    )
    if render.get("ok") and render.get("output_path"):
        if gen_result:
            render["video_gen"] = gen_result
        return str(render["output_path"]), render
    if gen_result and gen_result.get("ok"):
        return source, {"video_gen": gen_result, "mix_render": render}
    return video_path, render


def quality_gate(content: dict[str, Any]) -> dict[str, Any]:
    """发布前质检门禁。"""
    risk = content.get("risk_check") or {}
    script = str(content.get("script") or "").strip()
    checks = [
        {"name": "script_length", "pass": 30 <= len(script) <= 600, "detail": f"字数 {len(script)}"},
        {"name": "risk_check", "pass": bool(risk.get("passed")), "detail": risk.get("summary") or ""},
        {"name": "dedupe", "pass": not content.get("dedupe_duplicate"), "detail": (content.get("dedupe_info") or {}).get("recommendation") or ""},
        {"name": "channels", "pass": bool(content.get("channel_contents")), "detail": "多渠道文案就绪"},
    ]
    passed = all(c["pass"] for c in checks if c["name"] != "dedupe")  # 去重仅警告
    warnings = [c for c in checks if not c["pass"]]
    return {"passed": passed, "checks": checks, "warnings": warnings}


def build_publish_plan(
    *,
    platform: str,
    script: str,
    channels: list[str],
    cta: str,
    ad_bid_hint: str,
    provider: str,
    exec_url: str,
    ad_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "platform": platform,
        "channels": channels,
        "cta": cta,
        "ad_bid_hint": ad_bid_hint,
        "video_provider": provider,
        "steps": [
            {"step": 1, "action": "content_ready", "note": "脚本已由内容 Agent 生成"},
            {"step": 2, "action": "video_produce", "provider": provider, "reference": exec_url or "script_only"},
            {"step": 3, "action": "quality_check", "note": "发布前质检"},
            {"step": 4, "action": "publish", "platform": platform, "channels": channels},
            {"step": 5, "action": "ad_optimize", "hint": ad_bid_hint, "plan": ad_plan or {}},
        ],
    }

def build_channel_execution_list(channel_contents: dict[str, str], channels: list[str]) -> list[dict[str, str]]:
    mapping = {
        "short_video": "short_video_script",
        "moments_post": "moments_post",
        "dm_script": "dm_script",
        "community_post": "community_post",
        "poster_copy": "poster_copy",
    }
    out = []
    for ch in channels:
        key = mapping.get(ch, ch)
        text = channel_contents.get(key) or channel_contents.get(ch) or ""
        if text:
            out.append({"channel": ch, "content": text})
    return out


def _resolve_publish_platforms(goal: Any, strategy: dict[str, Any]) -> list[str]:
    extra = getattr(goal, "extra", {}) or {}
    raw = extra.get("publish_platforms") or extra.get("platforms")
    if isinstance(raw, list) and raw:
        return [str(x).strip().lower() for x in raw if str(x).strip()]
    plat = str(strategy.get("target_platform") or goal.platform or "douyin").strip().lower()
    return [plat]


def run_auto_publish(
    *,
    run_id: str,
    goal: Any,
    strategy: dict[str, Any],
    content: dict[str, Any],
    video_path: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    script = str(content.get("script") or "").strip()
    title = str(getattr(goal, "title", "") or strategy.get("primary_keyword") or "")[:30]
    platforms = _resolve_publish_platforms(goal, strategy)
    extra = getattr(goal, "extra", {}) or {}
    tags = extra.get("tags") if isinstance(extra.get("tags"), list) else None

    from services.publish.router import publish_multi

    result = publish_multi(
        platforms,
        video_path=video_path,
        script=script,
        title=title,
        dry_run=dry_run or bool(extra.get("publish_dry_run")),
    )
    if result.get("success") and not dry_run:
        metrics_record(run_id=run_id, event_type="publish_ok", value=float(result.get("success_count") or 0))
    return result


def start_execution_job(
    *,
    run_id: str,
    script: str,
    publish_plan: dict[str, Any],
    channel_execution: list[dict[str, str]],
    publish_results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    payload = {
        "script": script,
        "publish_plan": publish_plan,
        "channel_execution": channel_execution,
        "publish_results": publish_results or {},
        "status": "completed" if publish_results else "queued",
    }
    stage = "published" if publish_results and publish_results.get("success") else "queued"
    save_execution_job(job_id, run_id, stage, payload)
    metrics_record(run_id=run_id, event_type="execution_queued", payload={"job_id": job_id, "stage": stage})
    return {"job_id": job_id, "status": stage, "auto_started": True}


def build_execution(
    *,
    run_id: str,
    goal: Any,
    strategy: dict[str, Any],
    content: dict[str, Any],
    exec_url: str,
) -> dict[str, Any]:
    script = str(content.get("script") or "").strip()
    platform = str(strategy.get("target_platform") or goal.platform or "douyin")
    provider = str(strategy.get("selected_provider") or goal.video_provider or "template")
    channels = strategy.get("channels") or ["short_video"]
    channel_contents = content.get("channel_contents") or strategy.get("channel_preview") or {}
    video_path = str(getattr(goal, "video_path", "") or (getattr(goal, "extra", {}) or {}).get("video_path") or "").strip()
    keyword = str(strategy.get("primary_keyword") or getattr(goal, "keyword", "") or "")
    ad_plan = strategy.get("ad_plan") or build_ad_plan(
        keyword=keyword,
        platform=platform,
        strategy=strategy,
        perception={},
        budget_limit=float(getattr(goal, "budget_limit", 0) or 0),
    )
    qg = quality_gate(content)

    video_path, mix_render = _maybe_render_video(
        run_id=run_id,
        goal=goal,
        content=content,
        video_path=video_path,
        strategy=strategy,
    )

    slice_render = _maybe_render_slice_drafts(
        run_id=run_id,
        goal=goal,
        content=content,
        video_path=video_path,
        strategy=strategy,
    )
    if slice_render and slice_render.get("ok") and slice_render.get("recommended_path"):
        video_path = str(slice_render["recommended_path"])
        if isinstance(mix_render, dict):
            mix_render = {**mix_render, "slice_drafts": slice_render}
        else:
            mix_render = {"slice_drafts": slice_render}

    publish_plan = build_publish_plan(
        platform=platform,
        script=script,
        channels=channels,
        cta=strategy.get("cta") or "",
        ad_bid_hint=strategy.get("ad_bid_hint") or "",
        provider=provider,
        exec_url=exec_url,
        ad_plan=ad_plan,
    )
    channel_execution = build_channel_execution_list(channel_contents, channels)

    auto_started = False
    job_id = ""
    auto_error = ""
    publish_results: dict[str, Any] | None = None
    ad_deploy: dict[str, Any] | None = None

    extra = getattr(goal, "extra", {}) or {}
    sync_ad = bool(extra.get("sync_ad_api")) or bool(getattr(goal, "auto_execute", False))
    if sync_ad and ad_plan:
        ad_deploy = deploy_ad_plan(ad_plan, run_id=run_id, sync_api=bool(extra.get("sync_ad_api", True)))

    ad_report = None
    matrix_publish_result = None
    if ad_deploy and ad_deploy.get("campaign_id") and bool(extra.get("sync_ad_report", True)):
        try:
            from services.ad_feedback import sync_ad_report_for_run

            ad_report = sync_ad_report_for_run(run_id)
            if ad_report.get("ok"):
                ad_deploy["report"] = ad_report
        except Exception as exc:
            ad_deploy = ad_deploy or {}
            ad_deploy["report_error"] = str(exc)

    should_publish = bool(getattr(goal, "auto_publish", False)) and bool(video_path) and bool(script) and qg.get("passed")
    should_queue = bool(getattr(goal, "auto_execute", False)) and bool(script)

    review_result = None
    try:
        from services.review_queue import review_queue_enabled, submit_for_review

        want_review = review_queue_enabled() and bool(video_path) and bool(script) and qg.get("passed")
        want_review = want_review and not extra.get("skip_review")
        if want_review and slice_render and slice_render.get("ok") and len(slice_render.get("renders") or []) >= 2:
            try:
                from services.slice_drafts import submit_slice_drafts_for_review

                review_result = submit_slice_drafts_for_review(
                    run_id=run_id,
                    renders=list(slice_render.get("renders") or []),
                    title=str(getattr(goal, "title", "") or keyword)[:20],
                    payload={
                        "platform": platform,
                        "keyword": keyword,
                        "batch": "slice_drafts",
                        "org_id": str(getattr(goal, "org_id", "") or extra.get("org_id") or ""),
                    },
                    notify_feishu=bool(extra.get("notify_feishu", True)),
                )
                if review_result.get("ok"):
                    auto_started = True
                    should_publish = False
            except Exception as exc:
                review_result = {"ok": False, "error": str(exc)}
        elif want_review:
            review_result = submit_for_review(
                run_id=run_id,
                video_path=video_path,
                script=script,
                title=str(getattr(goal, "title", "") or keyword)[:30],
                payload={"platform": platform, "keyword": keyword},
                notify_feishu=bool(extra.get("notify_feishu", True)),
            )
            if review_result.get("ok"):
                auto_started = True
                should_publish = False
    except Exception as exc:
        review_result = {"ok": False, "error": str(exc)}

    if should_publish:
        try:
            publish_results = run_auto_publish(
                run_id=run_id,
                goal=goal,
                strategy=strategy,
                content=content,
                video_path=video_path,
            )
            if not publish_results.get("success"):
                auto_error = str(
                    (publish_results.get("results") or [{}])[0].get("error")
                    or publish_results.get("error")
                    or "publish_failed"
                )
        except Exception as exc:
            auto_error = str(exc)
            publish_results = {"ok": False, "error": str(exc)}

    if should_queue or should_publish:
        try:
            job = start_execution_job(
                run_id=run_id,
                script=script,
                publish_plan=publish_plan,
                channel_execution=channel_execution,
                publish_results=publish_results,
            )
            job_id = job.get("job_id") or ""
            auto_started = bool(job_id)
        except Exception as exc:
            if not auto_error:
                auto_error = str(exc)

    want_matrix = bool(getattr(goal, "auto_matrix_publish", False) or extra.get("auto_matrix_publish"))
    if want_matrix and video_path and script and qg.get("passed") and not extra.get("skip_matrix_publish"):
        try:
            from services.matrix_strategy import auto_matrix_publish

            matrix_publish_result = auto_matrix_publish(
                run_id=run_id,
                video_path=video_path,
                script=script,
                title=str(getattr(goal, "title", "") or keyword)[:30],
            )
            if matrix_publish_result.get("ok") and matrix_publish_result.get("action") != "skip":
                auto_started = True
        except Exception as exc:
            matrix_publish_result = {"ok": False, "error": str(exc)}

    return {
        "publish_plan": publish_plan,
        "prefilled_script": script,
        "execution_url": exec_url,
        "video_provider": provider,
        "video_path": video_path,
        "channel_execution": channel_execution,
        "publish_results": publish_results,
        "published": bool(publish_results and publish_results.get("success")),
        "job_id": job_id,
        "auto_started": auto_started,
        "auto_error": auto_error,
        "quality_gate": qg,
        "ad_optimize_plan": ad_plan,
        "ad_deploy": ad_deploy,
        "ad_report": ad_report,
        "matrix_publish": matrix_publish_result,
        "mix_render": mix_render,
        "slice_render": slice_render,
        "review": review_result,
        "ready": bool(script),
    }
