"""混剪计划与 ffmpeg 真实渲染。"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import bootstrap

GOLDEN_SEGMENTS = [    {"name": "钩子", "duration_sec": 3, "purpose": "3秒抓住注意力"},
    {"name": "痛点", "duration_sec": 9, "purpose": "共鸣用户场景"},
    {"name": "方案", "duration_sec": 13, "purpose": "给出解决步骤"},
    {"name": "证据", "duration_sec": 15, "purpose": "案例/数据背书"},
    {"name": "行动", "duration_sec": 15, "purpose": "CTA引导转化"},
]


def build_mix_plan(
    *,
    script: str,
    breakdown_segments: list[dict] | None = None,
    keyword: str = "",
) -> dict[str, Any]:
    segs = breakdown_segments or GOLDEN_SEGMENTS
    words = (script or "").replace("\n", " ").strip()
    chunks = _split_script(words, len(segs))

    timeline = []
    cursor = 0.0
    for i, seg in enumerate(segs[:5]):
        dur = float(seg.get("duration_sec") or seg.get("end", 10) - seg.get("start", 0) or 10)
        text = chunks[i] if i < len(chunks) else ""
        timeline.append(
            {
                "segment": seg.get("name") or f"段{i+1}",
                "start_sec": round(cursor, 1),
                "end_sec": round(cursor + dur, 1),
                "script_excerpt": text[:120],
                "edit_hint": seg.get("hint") or seg.get("purpose") or "口播+字幕",
                "b_roll_hint": _broll_hint(seg.get("name") or "", keyword),
            }
        )
        cursor += dur

    return {
        "total_duration_sec": round(cursor, 1),
        "timeline": timeline,
        "dedupe_note": "各段字幕样式保持一致，BGM 音量-18LUFS",
        "export_formats": ["9:16竖屏", "1080x1920", "H.264"],
    }


def _split_script(text: str, n: int) -> list[str]:
    if not text:
        return [""] * n
    sentences = re_split_sentences(text)
    if len(sentences) <= n:
        return sentences + [""] * (n - len(sentences))
    per = max(1, len(sentences) // n)
    out = []
    for i in range(n):
        chunk = sentences[i * per : (i + 1) * per if i < n - 1 else len(sentences)]
        out.append("".join(chunk))
    return out


def re_split_sentences(text: str) -> list[str]:
    import re

    parts = re.split(r"(?<=[。！？!?])", text)
    return [p.strip() for p in parts if p.strip()]


def _broll_hint(name: str, keyword: str) -> str:
    mapping = {
        "钩子": f"特写/反问字幕 + {keyword}相关画面",
        "痛点": "用户困扰场景混剪",
        "方案": "步骤演示/产品特写",
        "证据": "前后对比/数据图表",
        "行动": "评论区引导/私信截图",
    }
    return mapping.get(name, "通用口播画面")


def mix_enabled() -> bool:
    return os.environ.get("VIDEO_MIX_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def resolve_ffmpeg() -> str:
    env = (os.environ.get("FFMPEG_PATH") or "").strip()
    if env and Path(env).is_file():
        return env
    found = shutil.which("ffmpeg")
    return found or ""


def output_dir() -> Path:
    raw = (os.environ.get("VIDEO_OUTPUT_DIR") or "data/output/videos").strip()
    d = Path(raw)
    if not d.is_absolute():
        d = bootstrap.project_root() / d
    d.mkdir(parents=True, exist_ok=True)
    return d


def _escape_drawtext(text: str) -> str:
    s = (text or "").replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return s[:80]


def visual_dedup_enabled() -> bool:
    return os.environ.get("VISUAL_DEDUP_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def bgm_mix_enabled() -> bool:
    from services.bgm import bgm_enabled

    return bgm_enabled()


def _visual_seed(*, run_id: str, segment_idx: int, variant: str = "") -> random.Random:
    raw = f"{run_id}:{segment_idx}:{variant}".encode("utf-8")
    seed = int(hashlib.sha256(raw).hexdigest()[:8], 16)
    return random.Random(seed)


def _visual_filters(*, run_id: str, segment_idx: int, variant: str = "") -> str:
    """随机滤镜/变速（可复现）。"""
    if not visual_dedup_enabled():
        return ""
    rng = _visual_seed(run_id=run_id, segment_idx=segment_idx, variant=variant)
    try:
        smin = float(os.environ.get("VISUAL_DEDUP_SPEED_MIN", "0.97"))
        smax = float(os.environ.get("VISUAL_DEDUP_SPEED_MAX", "1.03"))
    except ValueError:
        smin, smax = 0.97, 1.03
    speed = round(rng.uniform(smin, smax), 3)
    brightness = round(rng.uniform(-0.03, 0.05), 3)
    contrast = round(rng.uniform(0.98, 1.08), 3)
    hue = round(rng.uniform(-8, 8), 1)
    parts = [f"setpts=PTS/{speed}", f"eq=brightness={brightness}:contrast={contrast}", f"hue=h={hue}"]
    if os.environ.get("VISUAL_DEDUP_PIP_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on"):
        # 右上角半透明色块画中画（轻量差异化）
        color = rng.choice(["0x222222", "0x333355", "0x223322"])
        parts.append(
            f"drawbox=x=w*0.72:y=h*0.05:w=w*0.22:h=h*0.12:color={color}@0.35:t=fill"
        )
    return ",".join(parts)


def _segment_clip(
    *,
    input_path: Path,
    start: float,
    duration: float,
    subtitle: str,
    out_path: Path,
    ffmpeg: str,
    run_id: str = "",
    segment_idx: int = 0,
    variant: str = "",
) -> None:
    vf_parts = [
        "scale=1080:1920:force_original_aspect_ratio=decrease",
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
    ]
    visual = _visual_filters(run_id=run_id, segment_idx=segment_idx, variant=variant)
    if visual:
        vf_parts.append(visual)
    vf_parts.append(
        f"drawtext=text='{_escape_drawtext(subtitle)}':fontsize=42:fontcolor=white:"
        f"borderw=2:bordercolor=black:x=(w-text_w)/2:y=h*0.78"
    )
    vf = ",".join(vf_parts)
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        str(max(0, start)),
        "-i",
        str(input_path),
        "-t",
        str(max(0.5, duration)),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-an",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)


def _concat_clips(clip_paths: list[Path], output_path: Path, ffmpeg: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = output_path.with_suffix(".txt")
    lines = [f"file '{p.resolve().as_posix()}'" for p in clip_paths]
    list_file.write_text("\n".join(lines), encoding="utf-8")
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    try:
        list_file.unlink(missing_ok=True)
    except OSError:
        pass


def _attach_bgm(video_path: Path, bgm_path: str, ffmpeg: str) -> dict[str, Any]:
    from services.bgm import bgm_volume

    bgm = Path(bgm_path).expanduser()
    if not bgm.is_file():
        return {"ok": False, "reason": "bgm_file_missing", "path": str(bgm)}
    vol = bgm_volume()
    out = video_path.with_name(video_path.stem + "_bgm.mp4")
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-stream_loop",
        "-1",
        "-i",
        str(bgm),
        "-filter_complex",
        f"[1:a]volume={vol}[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map",
        "0:v",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(out),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    except subprocess.CalledProcessError:
        cmd2 = [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-stream_loop",
            "-1",
            "-i",
            str(bgm),
            "-filter_complex",
            f"[1:a]volume={vol}[aout]",
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(out),
        ]
        try:
            subprocess.run(cmd2, check=True, capture_output=True, timeout=180)
        except subprocess.CalledProcessError as exc2:
            return {
                "ok": False,
                "error": "ffmpeg_bgm_failed",
                "stderr": (exc2.stderr or b"").decode("utf-8", errors="replace")[:300],
            }
    return {"ok": True, "output_path": str(out.resolve()), "bgm_path": str(bgm), "volume": vol}


def render_mix_video(
    *,
    mix_plan: dict[str, Any],
    source_video: str,
    output_name: str = "",
    run_id: str = "",
    script: str = "",
    enable_tts: bool = True,
    voice: str = "",
    keyword: str = "",
    variant: str = "",
    product_image: str = "",
) -> dict[str, Any]:
    """按 mix_plan 时间轴用 ffmpeg 切片、字幕叠加、TTS 配音并拼接。"""
    if not mix_enabled():
        return {"ok": False, "error": "video_mix_disabled"}
    ffmpeg = resolve_ffmpeg()
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg_not_found", "hint": "安装 ffmpeg 或设置 FFMPEG_PATH"}

    src = Path(source_video).expanduser()
    if not src.is_file():
        return {"ok": False, "error": "source_video_missing", "path": str(src)}

    timeline = mix_plan.get("timeline") or []
    if not timeline:
        return {"ok": False, "error": "empty_timeline"}

    out_dir = output_dir()
    stem = output_name or f"mix_{run_id[:8] if run_id else 'out'}"
    final_path = out_dir / f"{stem}.mp4"

    with tempfile.TemporaryDirectory(prefix="matrix_mix_") as tmp:
        tmp_dir = Path(tmp)
        clips: list[Path] = []
        seg_start = 0.0
        for i, seg in enumerate(timeline):
            dur = float(seg.get("end_sec", 0) - seg.get("start_sec", 0)) or 3.0
            clip = tmp_dir / f"seg_{i:02d}.mp4"
            try:
                _segment_clip(
                    input_path=src,
                    start=seg_start,
                    duration=dur,
                    subtitle=str(seg.get("script_excerpt") or seg.get("segment") or ""),
                    out_path=clip,
                    ffmpeg=ffmpeg,
                    run_id=run_id,
                    segment_idx=i,
                    variant=variant,
                )
                clips.append(clip)
                seg_start += dur
            except subprocess.CalledProcessError as exc:
                return {
                    "ok": False,
                    "error": "ffmpeg_segment_failed",
                    "segment": i,
                    "stderr": (exc.stderr or b"").decode("utf-8", errors="replace")[:500],
                }

        try:
            _concat_clips(clips, final_path, ffmpeg)
        except subprocess.CalledProcessError as exc:
            return {
                "ok": False,
                "error": "ffmpeg_concat_failed",
                "stderr": (exc.stderr or b"").decode("utf-8", errors="replace")[:500],
            }

    tts_result = None
    if enable_tts and (script or "").strip():
        tts_result = _attach_tts(final_path, script, ffmpeg, mix_plan.get("total_duration_sec") or 55, voice=voice)
        if tts_result.get("ok") and tts_result.get("output_path"):
            final_path = Path(tts_result["output_path"])

    bgm_result = None
    if bgm_mix_enabled():
        from services.bgm import pick_bgm_for_mix

        bgm_meta = pick_bgm_for_mix(keyword=keyword or str(mix_plan.get("keyword") or ""), mix_plan=mix_plan)
        bgm_path = str(bgm_meta.get("path") or "")
        if bgm_path:
            bgm_result = _attach_bgm(final_path, bgm_path, ffmpeg)
            if bgm_result.get("ok") and bgm_result.get("output_path"):
                final_path = Path(bgm_result["output_path"])

    product_result = None
    if product_image:
        try:
            from services.product_compose import attach_product_image

            product_result = attach_product_image(final_path, product_image)
            if product_result.get("ok") and product_result.get("output_path"):
                final_path = Path(product_result["output_path"])
        except Exception:
            product_result = {"ok": False}

    return {
        "ok": True,
        "output_path": str(final_path.resolve()),
        "duration_sec": mix_plan.get("total_duration_sec"),
        "segments_rendered": len(clips),
        "ffmpeg": ffmpeg,
        "tts": tts_result,
        "bgm": bgm_result,
        "product_compose": product_result,
        "voice": voice,
        "visual_dedup": visual_dedup_enabled(),
    }


def _attach_tts(video_path: Path, script: str, ffmpeg: str, duration_hint: float, *, voice: str = "", audio_path: str = "") -> dict[str, Any]:
    from services.tts import synthesize_speech

    if audio_path and Path(audio_path).is_file():
        tts = {"ok": True, "output_path": audio_path, "provider": "prebuilt", "voice": voice}
    else:
        audio_out = video_path.with_suffix(".voice.mp3")
        tts = synthesize_speech(script, output_path=audio_out, voice=voice or "", duration_hint_sec=float(duration_hint or 0))
    if not tts.get("ok"):
        return tts

    suffix = f"_{voice.split('-')[-1][:8]}" if voice else "_voiced"
    voiced = video_path.with_name(video_path.stem + suffix + ".mp4")
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(tts["output_path"]),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(voiced),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    except subprocess.CalledProcessError as exc:
        return {
            "ok": False,
            "error": "ffmpeg_mux_failed",
            "stderr": (exc.stderr or b"").decode("utf-8", errors="replace")[:300],
            "tts": tts,
        }
    return {"ok": True, "output_path": str(voiced.resolve()), "tts": tts, "voice": voice}


def render_ab_mix_videos(
    *,
    mix_plan: dict[str, Any],
    source_video: str,
    script: str,
    tts_variants: dict[str, Any],
    run_id: str = "",
) -> dict[str, Any]:
    """为 A/B 音色各渲染一条配音成片。"""
    outputs: list[dict[str, Any]] = []
    for var in (tts_variants.get("variants") or []):
        if not var.get("ok"):
            continue
        name = f"mix_{run_id[:6] if run_id else 'ab'}_{var.get('variant', 'X')}"
        base = render_mix_video(
            mix_plan=mix_plan,
            source_video=source_video,
            run_id=run_id,
            output_name=name,
            script=script,
            enable_tts=False,
            variant=str(var.get("variant") or "X"),
        )
        if not base.get("ok"):
            outputs.append({**var, "render": base})
            continue
        ffmpeg = base.get("ffmpeg") or resolve_ffmpeg()
        mux = _attach_tts(
            Path(base["output_path"]),
            script,
            ffmpeg,
            float(mix_plan.get("total_duration_sec") or 55),
            voice=str(var.get("voice") or ""),
            audio_path=str(var.get("output_path") or ""),
        )
        outputs.append({**var, "base_video": base.get("output_path"), "render": mux})

    ok = [o for o in outputs if (o.get("render") or {}).get("ok")]
    return {
        "ok": bool(ok),
        "variants": outputs,
        "recommended": tts_variants.get("recommended"),
        "count": len(ok),
    }
