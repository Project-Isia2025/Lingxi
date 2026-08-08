"""项目根路径初始化（独立项目，不依赖外部宿主）。"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent


def project_root() -> Path:
    return _ROOT


def ensure_paths() -> Path:
    root = project_root()
    s = str(root)
    if s not in sys.path:
        sys.path.insert(0, s)
    return root


def _sync_settings() -> None:
    try:
        from config.settings import sync_settings_to_environ

        sync_settings_to_environ()
    except Exception:
        pass


def load_local_env() -> None:
    """加载 config/local.env 到进程环境（不覆盖已有变量），并同步 pydantic Settings。"""
    import os

    path = project_root() / "config" / "local.env"
    if path.is_file():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip()
                if key and key not in os.environ:
                    os.environ[key] = val
        except OSError:
            pass
    _sync_settings()
