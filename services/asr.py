"""视频/音频 ASR 转写。"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import bootstrap


def asr_enabled() -> bool:
    return os.environ.get("ASR_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def resolve_ffmpeg() -> str:
    env = (os.environ.get("FFMPEG_PATH") or "").strip()
    if env and Path(env).is_file():
        return env
    import shutil

    return shutil.which("ffmpeg") or "ffmpeg"


def extract_audio(video_path: str | Path, *, output_path: Path | None = None) -> Path:
    src = Path(video_path).expanduser()
    if not src.is_file():
        raise FileNotFoundError(str(src))
    out = output_path or Path(tempfile.mkstemp(suffix=".wav")[1])
    cmd = [
        resolve_ffmpeg(),
        "-y",
        "-i",
        str(src),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    return out


def transcribe_audio_file(audio_path: str | Path) -> dict[str, Any]:
    if not asr_enabled():
        return {"ok": False, "error": "asr_disabled"}
    path = Path(audio_path)
    if not path.is_file():
        return {"ok": False, "error": "audio_not_found"}

    api_base = (os.environ.get("ASR_API_BASE") or os.environ.get("OPENAI_BASE_URL") or os.environ.get("LLM_API_BASE") or "").strip().rstrip("/")
    api_key = (os.environ.get("ASR_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY") or "").strip()
    model = (os.environ.get("ASR_MODEL") or "whisper-1").strip()

    if api_base and api_key:
        try:
            import requests

            with open(path, "rb") as f:
                resp = requests.post(
                    f"{api_base}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": (path.name, f, "audio/wav")},
                    data={"model": model, "language": os.environ.get("ASR_LANGUAGE", "zh")},
                    timeout=int(os.environ.get("ASR_TIMEOUT_SEC", "120")),
                )
            resp.raise_for_status()
            data = resp.json()
            text = str(data.get("text") or data.get("transcript") or "").strip()
            if text:
                return {"ok": True, "text": text[:8000], "provider": "api", "model": model}
        except Exception as exc:
            return {"ok": False, "error": "asr_api_failed", "detail": str(exc)[:300]}

    return {"ok": False, "error": "asr_not_configured", "hint": "配置 ASR_API_BASE + ASR_API_KEY 或 OPENAI API"}


def transcribe_video(video_path: str | Path) -> dict[str, Any]:
    """从视频提取音频并转写。"""
    if not asr_enabled():
        return {"ok": False, "error": "asr_disabled"}
    try:
        audio = extract_audio(video_path)
        result = transcribe_audio_file(audio)
        result["video_path"] = str(Path(video_path).resolve())
        try:
            if str(audio).endswith(".wav") and "tmp" in str(audio):
                audio.unlink(missing_ok=True)
        except OSError:
            pass
        return result
    except subprocess.CalledProcessError as exc:
        return {
            "ok": False,
            "error": "ffmpeg_extract_failed",
            "stderr": (exc.stderr or b"").decode("utf-8", errors="replace")[:300],
        }
    except Exception as exc:
        return {"ok": False, "error": "transcribe_failed", "detail": str(exc)}


def transcribe_url(video_url: str, *, download_path: Path | None = None) -> dict[str, Any]:
    """下载视频 URL 并转写（需 network）。"""
    from urllib.request import Request, urlopen

    if not str(video_url).startswith("http"):
        return {"ok": False, "error": "invalid_url"}
    out = download_path or bootstrap.project_root() / "data" / "tmp" / "asr_download.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = Request(video_url, headers={"User-Agent": "MatrixAgent/1.0"})
        with urlopen(req, timeout=30) as resp:
            out.write_bytes(resp.read())
    except Exception as exc:
        return {"ok": False, "error": "download_failed", "detail": str(exc)[:200]}
    result = transcribe_video(out)
    result["source_url"] = video_url
    return result
