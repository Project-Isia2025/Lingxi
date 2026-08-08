"""Playwright 创作者中心上传页 smoke 探测（不点击发布）。"""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from services.publish.common import build_metadata, publish_enabled, resolve_storage, validate_video_path
from services.publish.playwright_util import playwright_installed
from services.publish.router import PLATFORM_CONFIGS


def smoke_enabled() -> bool:
    return os.environ.get("PUBLISH_SMOKE_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def smoke_submit_enabled() -> bool:
    return os.environ.get("PUBLISH_SMOKE_SUBMIT_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def _run_with_headless(cfg, headed: bool | None):
    import os as _os

    key = cfg.headless_env
    prev = _os.environ.get(key)
    if headed is not None:
        _os.environ[key] = "0" if headed else "1"
        return key, prev
    return key, None


def _restore_headless(key: str, prev: str | None) -> None:
    import os as _os

    if prev is None:
        return
    if prev == "":
        _os.environ.pop(key, None)
    else:
        _os.environ[key] = prev


def probe_publish_upload(
    *,
    platform: str,
    video_path: str = "",
    script: str = "Smoke 探测：上传页可达性测试。",
    title: str = "Smoke探测",
    account_id: str = "default",
    headed: bool | None = None,
    submit: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    """打开创作者中心上传页探测；submit=True 且 confirm=True 时真实发布。"""
    if submit and not confirm:
        return {"ok": False, "error": "submit_requires_confirm", "hint": "真实发布请加 --confirm"}

    if not smoke_enabled():
        return {"ok": False, "error": "publish_smoke_disabled"}

    plat = platform.strip().lower()
    if plat == "xhs":
        plat = "xiaohongshu"
    if plat not in PLATFORM_CONFIGS:
        return {"ok": False, "error": f"unsupported_platform:{plat}"}

    if not playwright_installed():
        return {"ok": False, "error": "playwright_not_installed"}

    if not publish_enabled(plat):
        return {"ok": False, "error": "publish_disabled", "platform": plat}

    storage = resolve_storage(plat, account_id=account_id)
    if not storage:
        return {"ok": False, "error": "storage_state_missing", "platform": plat}

    local_video = video_path
    temp_video = ""
    if not local_video:
        td = tempfile.mkdtemp(prefix="pub-smoke-")
        temp_video = str(Path(td) / f"smoke_{uuid.uuid4().hex[:6]}.mp4")
        Path(temp_video).write_bytes(b"\x00" * 1200)
        local_video = temp_video

    ok, err = validate_video_path(local_video)
    if not ok:
        return {"ok": False, "error": err}

    cfg_fn = PLATFORM_CONFIGS[plat]
    cfg = cfg_fn()
    metadata = build_metadata(script=script, title=title)

    key, prev = _run_with_headless(cfg, headed)
    try:
        from services.publish.creator_engine import run_publish

        timeout = int(os.environ.get("PUBLISH_PROBE_TIMEOUT_SEC", "120"))
        if submit:
            timeout = int(os.environ.get("PUBLISH_TIMEOUT_SEC", "240"))
        result = run_publish(
            cfg,
            video_path=local_video,
            metadata=metadata,
            storage_state=storage,
            timeout_sec=timeout,
            probe_only=not submit,
        )
    finally:
        _restore_headless(key, prev)
        if temp_video:
            try:
                Path(temp_video).unlink(missing_ok=True)
            except Exception:
                pass

    success = bool(result.get("success"))
    return {
        "ok": success,
        "platform": plat,
        "probe": not submit,
        "submitted": submit,
        "storage_state": storage,
        "result": result,
        "error": result.get("error") if not success else "",
    }
