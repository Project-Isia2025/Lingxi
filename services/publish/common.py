"""发布共用：元数据、配额、登录态路径。"""
from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import bootstrap

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TAG_POOL = ["短视频", "干货", "口播", "获客", "运营"]


def env_truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def project_root() -> Path:
    return bootstrap.project_root()


def resolve_storage(platform: str, account_id: str = "default") -> str:
    plat = platform.lower()
    if plat == "xhs":
        plat = "xiaohongshu"
    try:
        from core.storage import list_publish_accounts

        for acc in list_publish_accounts(platform=plat, enabled_only=False):
            if str(acc.get("account_id") or "") == account_id:
                raw = str(acc.get("storage_state") or "").strip()
                if raw:
                    p = Path(raw).expanduser()
                    if not p.is_absolute():
                        p = project_root() / p
                    if p.is_file():
                        return str(p.resolve())
    except Exception:
        pass
    key = f"{plat.upper()}_PUBLISH_STORAGE_STATE"
    if plat == "xiaohongshu":
        key = "XHS_PUBLISH_STORAGE_STATE"
    raw = (os.environ.get(key) or "").strip()
    if raw and Path(raw).expanduser().is_file():
        return str(Path(raw).expanduser().resolve())
    defaults = {
        "douyin": project_root() / "data" / "state" / "douyin_creator_storage.json",
        "xiaohongshu": project_root() / "data" / "state" / "xhs_creator_storage.json",
        "xhs": project_root() / "data" / "state" / "xhs_creator_storage.json",
        "shipinhao": project_root() / "data" / "state" / "shipinhao_creator_storage.json",
    }
    p = defaults.get(plat)
    return str(p.resolve()) if p and p.is_file() else ""


def publish_enabled(platform: str) -> bool:
    key = f"{platform.upper()}_PUBLISH_ENABLED"
    if not env_truthy(key, "1"):
        return False
    from services.publish.playwright_util import playwright_installed

    return playwright_installed()


def build_metadata(*, script: str, title: str = "", tags: list[str] | None = None) -> dict[str, Any]:
    hook = (script or "").strip().replace("\n", " ")[:28] or "AI口播视频"
    t = (title or hook).strip()[:30]
    tag_list = tags or TAG_POOL[:3]
    disclosure = os.environ.get("PUBLISH_AI_DISCLOSURE", "本内容含AI辅助创作").strip()
    return {
        "title": t,
        "script": script,
        "tags": tag_list,
        "ai_disclosure_text": disclosure,
    }


def validate_video_path(video_path: str) -> tuple[bool, str]:
    p = Path(str(video_path or "").strip())
    if not p.is_file():
        return False, f"视频不存在: {p}"
    if p.stat().st_size < 800:
        return False, f"视频文件过小: {p}"
    return True, ""


def public_url_validator(url: str, *, allow_hosts: tuple[str, ...], path_hints: tuple[str, ...] = ()) -> str:
    u = str(url or "").strip()
    if not u.startswith(("http://", "https://")):
        return ""
    try:
        host = (urlparse(u).netloc or "").lower()
        path = (urlparse(u).path or "").lower()
    except Exception:
        return ""
    if not any(host.endswith(h) for h in allow_hosts):
        return ""
    if path_hints and not any(h in path for h in path_hints):
        if "creator." in host:
            return ""
    return u[:2048]


def check_publish_quota(platform: str, account_id: str = "default") -> tuple[bool, str]:
    from core.storage import get_publish_state

    record = get_publish_state(platform, account_id)
    now = int(time.time())
    today = datetime.now().strftime("%Y-%m-%d")
    limit = int(os.environ.get("PUBLISH_DAILY_LIMIT", "4"))
    min_interval = int(os.environ.get("PUBLISH_MIN_INTERVAL_SEC", "300"))
    last_ts = int(record.get("last_publish_ts") or 0)
    day = str(record.get("last_day") or "")
    count = int(record.get("day_count") or 0) if day == today else 0
    if count >= limit:
        return False, f"已达日上限 {limit} 条"
    if last_ts and now - last_ts < min_interval:
        return False, f"发布间隔不足 {min_interval}s"
    return True, ""


def mark_published(platform: str, account_id: str = "default") -> None:
    from core.storage import set_publish_state

    now = int(time.time())
    today = datetime.now().strftime("%Y-%m-%d")
    from core.storage import get_publish_state

    record = get_publish_state(platform, account_id)
    day = str(record.get("last_day") or "")
    count = int(record.get("day_count") or 0) if day == today else 0
    set_publish_state(
        platform,
        account_id,
        {"last_publish_ts": now, "last_day": today, "day_count": count + 1},
    )
