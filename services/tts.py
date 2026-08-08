"""TTS 配音：edge-tts / OpenAI 兼容 / ffmpeg 静音兜底。"""
from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import bootstrap


def tts_enabled() -> bool:
    return os.environ.get("TTS_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def default_voice() -> str:
    return (os.environ.get("TTS_VOICE") or "zh-CN-XiaoxiaoNeural").strip()


def ab_voices() -> list[str]:
    raw = (os.environ.get("TTS_AB_VOICES") or "zh-CN-XiaoxiaoNeural,zh-CN-YunxiNeural").strip()
    voices = [v.strip() for v in raw.split(",") if v.strip()]
    return voices[:3]


def ab_enabled() -> bool:
    return os.environ.get("TTS_AB_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def _edge_tts_available() -> bool:
    try:
        import edge_tts  # noqa: F401

        return True
    except ImportError:
        return False


async def _edge_synthesize(text: str, output_path: Path, voice: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))


def _openai_tts(text: str, output_path: Path) -> dict[str, Any]:
    import requests

    base = (os.environ.get("TTS_API_BASE") or os.environ.get("LLM_API_BASE") or "").strip().rstrip("/")
    key = (os.environ.get("TTS_API_KEY") or os.environ.get("LLM_API_KEY") or "").strip()
    model = (os.environ.get("TTS_MODEL") or "tts-1").strip()
    voice = (os.environ.get("TTS_OPENAI_VOICE") or "alloy").strip()
    if not base or not key:
        return {"ok": False, "error": "tts_api_not_configured"}
    resp = requests.post(
        f"{base}/audio/speech",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "input": text[:4096], "voice": voice},
        timeout=int(os.environ.get("TTS_TIMEOUT_SEC", "60")),
    )
    resp.raise_for_status()
    output_path.write_bytes(resp.content)
    return {"ok": True, "provider": "openai_compatible"}


def _ffmpeg_silent(output_path: Path, duration_sec: float, ffmpeg: str) -> None:
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            str(max(1.0, duration_sec)),
            "-q:a",
            "9",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )


def synthesize_speech(
    text: str,
    *,
    output_path: str | Path | None = None,
    voice: str = "",
    duration_hint_sec: float = 0,
) -> dict[str, Any]:
    """生成口播配音 mp3。"""
    if not tts_enabled():
        return {"ok": False, "error": "tts_disabled"}

    raw = (text or "").strip()
    if not raw:
        return {"ok": False, "error": "empty_text"}

    out = Path(output_path) if output_path else Path(tempfile.mkstemp(suffix=".mp3")[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    voice = voice or default_voice()

    if _edge_tts_available():
        try:
            asyncio.run(_edge_synthesize(raw[:4096], out, voice))
            return {"ok": True, "output_path": str(out.resolve()), "provider": "edge_tts", "voice": voice}
        except Exception as exc:
            last_err = str(exc)
    else:
        last_err = "edge_tts_not_installed"

    try:
        oai = _openai_tts(raw, out)
        if oai.get("ok"):
            oai["output_path"] = str(out.resolve())
            oai["voice"] = voice
            return oai
    except Exception as exc:
        last_err = str(exc)

    ffmpeg = os.environ.get("FFMPEG_PATH") or "ffmpeg"
    try:
        dur = duration_hint_sec or max(5.0, len(raw) / 5.0)
        silent = out.with_suffix(".silent.mp3")
        _ffmpeg_silent(silent, dur, ffmpeg)
        return {
            "ok": True,
            "output_path": str(silent.resolve()),
            "provider": "silent_fallback",
            "degraded": True,
            "warning": last_err,
        }
    except Exception as exc:
        return {"ok": False, "error": "tts_all_failed", "detail": str(exc), "warning": last_err}


def synthesize_ab_variants(
    text: str,
    *,
    voices: list[str] | None = None,
    output_dir: str | Path | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    """多音色 A/B 配音，返回 variant A/B/C 音频路径。"""
    if not ab_enabled() or not tts_enabled():
        return {"ok": False, "error": "tts_ab_disabled"}

    raw = (text or "").strip()
    if not raw:
        return {"ok": False, "error": "empty_text"}

    voice_list = voices or ab_voices()
    base_dir = Path(output_dir) if output_dir else bootstrap.project_root() / "data" / "output" / "tts"
    base_dir.mkdir(parents=True, exist_ok=True)
    stem = run_id[:8] if run_id else "ab"

    variants: list[dict[str, Any]] = []
    labels = ["A", "B", "C"]
    for i, voice in enumerate(voice_list[:3]):
        label = labels[i] if i < len(labels) else f"V{i+1}"
        out = base_dir / f"{stem}_voice_{label}.mp3"
        row = synthesize_speech(raw, output_path=out, voice=voice)
        variants.append(
            {
                "variant": label,
                "voice": voice,
                "ok": bool(row.get("ok")),
                "output_path": row.get("output_path"),
                "provider": row.get("provider"),
                "error": row.get("error"),
            }
        )

    ok_variants = [v for v in variants if v.get("ok")]
    return {
        "ok": bool(ok_variants),
        "variants": variants,
        "recommended": ok_variants[0]["variant"] if ok_variants else "",
        "count": len(ok_variants),
    }
