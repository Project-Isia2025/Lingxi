"""AI 视频 provider 共享 HTTP 客户端（提交 + 轮询 + 下载）。"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import bootstrap


def poll_timeout_sec() -> float:
    try:
        return float(os.environ.get("VIDEO_GEN_TIMEOUT_SEC", "900"))
    except ValueError:
        return 900.0


def poll_interval_sec() -> float:
    try:
        return max(2.0, float(os.environ.get("VIDEO_GEN_POLL_INTERVAL_SEC", "5")))
    except ValueError:
        return 5.0


def output_dir() -> Path:
    raw = (os.environ.get("VIDEO_OUTPUT_DIR") or "data/output/videos").strip()
    d = Path(raw)
    if not d.is_absolute():
        d = bootstrap.project_root() / d
    d.mkdir(parents=True, exist_ok=True)
    return d


def api_credentials(provider: str) -> tuple[str, str]:
    pid = (provider or "").strip().upper()
    return (
        (os.environ.get(f"{pid}_API_KEY") or "").strip(),
        (os.environ.get(f"{pid}_API_URL") or "").strip(),
    )


def download_to_local(url: str, *, run_id: str, provider: str, task_id: str = "") -> dict[str, Any]:
    import requests

    out = output_dir() / f"gen_{provider}_{run_id[:8] or uuid.uuid4().hex[:8]}.mp4"
    try:
        with requests.get(url, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with open(out, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
        return {"ok": True, "output_path": str(out.resolve()), "provider": provider, "mode": "api", "task_id": task_id}
    except Exception as exc:
        return {"ok": False, "error": "download_failed", "detail": str(exc)[:200]}


def http_produce_task(
    *,
    provider: str,
    api_url: str,
    api_key: str,
    payload: dict[str, Any],
    run_id: str,
    auth_header: str = "Bearer",
) -> dict[str, Any]:
    """POST 创建任务并轮询直到完成或超时。"""
    import requests

    headers = {"Authorization": f"{auth_header} {api_key}", "Content-Type": "application/json"}
    try:
        resp = requests.post(api_url, json=payload, headers=headers, timeout=30)
        if resp.status_code >= 400:
            return {
                "ok": False,
                "error": f"{provider}_api_error",
                "status": resp.status_code,
                "body": resp.text[:300],
            }
        data = resp.json() if resp.content else {}
    except Exception as exc:
        return {"ok": False, "error": f"{provider}_request_failed", "detail": str(exc)[:300]}

    task_id = str(data.get("task_id") or data.get("id") or data.get("job_id") or "")
    direct_url = str(data.get("output_url") or data.get("video_url") or data.get("result_url") or "")
    if direct_url:
        out = download_to_local(direct_url, run_id=run_id, provider=provider)
        out["payload_sent"] = {k: payload.get(k) for k in list(payload.keys())[:8]}
        return out

    if not task_id:
        return {"ok": False, "error": f"{provider}_no_task_id", "response": data}

    poll_url = str(data.get("poll_url") or api_url.rstrip("/") + f"/{task_id}")
    deadline = time.time() + poll_timeout_sec()
    while time.time() < deadline:
        time.sleep(poll_interval_sec())
        try:
            pr = requests.get(poll_url, headers=headers, timeout=20)
            pdata = pr.json() if pr.content else {}
        except Exception as exc:
            return {"ok": False, "error": f"{provider}_poll_failed", "detail": str(exc)[:200], "task_id": task_id}
        status = str(pdata.get("status") or pdata.get("state") or "").lower()
        if status in ("success", "succeeded", "done", "completed"):
            url = str(pdata.get("output_url") or pdata.get("video_url") or pdata.get("result_url") or "")
            if url:
                return download_to_local(url, run_id=run_id, provider=provider, task_id=task_id)
            break
        if status in ("failed", "error", "cancelled"):
            return {"ok": False, "error": f"{provider}_task_failed", "task_id": task_id, "response": pdata}
    return {"ok": False, "error": f"{provider}_timeout", "task_id": task_id}


def mock_copy_source(
    *,
    provider: str,
    run_id: str,
    source_video: str,
    hint: str = "",
) -> dict[str, Any]:
    import shutil

    src = Path(source_video).expanduser() if source_video else None
    out = output_dir() / f"mock_{provider}_{run_id[:8] or 'out'}.mp4"
    if src and src.is_file():
        shutil.copy2(src, out)
        return {
            "ok": True,
            "output_path": str(out.resolve()),
            "provider": provider,
            "mode": "mock",
            "hint": hint or f"未配置 {provider.upper()} API，已复制 source_video",
        }
    return {
        "ok": False,
        "error": f"{provider}_mock_no_source",
        "hint": hint or f"配置 {provider.upper()}_API_KEY 与 {provider.upper()}_API_URL",
    }


def mock_image_to_video(
    *,
    provider: str,
    run_id: str,
    image_path: str,
    duration_sec: float = 15.0,
) -> dict[str, Any]:
    """用商品图/人像图生成占位竖屏视频（数字人无 Key 联调）。"""
    from services.video_mix import resolve_ffmpeg

    img = Path(image_path).expanduser()
    if not img.is_file():
        return {"ok": False, "error": f"{provider}_mock_no_image"}
    ffmpeg = resolve_ffmpeg()
    if not ffmpeg:
        return mock_copy_source(provider=provider, run_id=run_id, source_video="", hint="ffmpeg_missing_for_image_mock")

    out = output_dir() / f"mock_{provider}_{run_id[:8] or 'img'}.mp4"
    dur = max(3.0, float(duration_sec))
    cmd = [
        ffmpeg,
        "-y",
        "-loop",
        "1",
        "-i",
        str(img.resolve()),
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t",
        str(dur),
        "-vf",
        "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(out),
    ]
    import subprocess

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    except subprocess.CalledProcessError as exc:
        return {
            "ok": False,
            "error": f"{provider}_image_mock_failed",
            "stderr": (exc.stderr or b"").decode("utf-8", errors="replace")[:300],
        }
    return {
        "ok": True,
        "output_path": str(out.resolve()),
        "provider": provider,
        "mode": "mock_image",
        "hint": f"未配置 {provider.upper()} API，已由商品图生成 {dur:.0f}s 占位竖屏视频",
    }
