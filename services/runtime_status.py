"""运行时与自启动状态（Windows 计划任务 / systemd / 进程健康）。"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import bootstrap


def project_root() -> Path:
    return bootstrap.project_root()


def _api_port() -> int:
    try:
        return int(os.environ.get("API_PORT", "9200"))
    except ValueError:
        return 9200


def probe_api_health(*, host: str = "127.0.0.1", timeout_sec: float = 2.0) -> dict[str, Any]:
    port = _api_port()
    url = f"http://{host}:{port}/api/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            import json

            body = json.loads(resp.read().decode("utf-8"))
            return {"ok": True, "reachable": True, "url": url, "body": body}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "reachable": True, "url": url, "error": f"http_{exc.code}"}
    except Exception as exc:
        return {"ok": False, "reachable": False, "url": url, "error": str(exc)[:160]}


def _worker_status() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        from services.publish_worker import get_worker_status

        out["publish_queue"] = get_worker_status()
    except Exception as exc:
        out["publish_queue"] = {"ok": False, "error": str(exc)[:120]}
    try:
        from services.post_publish_monitor_worker import get_status

        out["post_publish_monitor"] = get_status()
    except Exception as exc:
        out["post_publish_monitor"] = {"ok": False, "error": str(exc)[:120]}
    try:
        from services.perception_scheduler import get_scheduler_status

        out["perception_scheduler"] = get_scheduler_status()
    except Exception as exc:
        out["perception_scheduler"] = {"ok": False, "error": str(exc)[:120]}
    return out


def _windows_task_status(task_name: str) -> dict[str, Any]:
    if platform.system().lower() != "windows":
        return {"exists": False, "state": "unsupported", "task_name": task_name}
    try:
        proc = subprocess.run(
            ["schtasks", "/Query", "/TN", task_name, "/FO", "LIST"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            return {"exists": False, "state": "missing", "task_name": task_name}
        state = "unknown"
        for line in (proc.stdout or "").splitlines():
            if line.strip().lower().startswith("status:"):
                state = line.split(":", 1)[1].strip().lower()
                break
        return {"exists": True, "state": state, "task_name": task_name}
    except Exception as exc:
        return {"exists": False, "state": "error", "task_name": task_name, "error": str(exc)[:120]}


def windows_autostart_status(*, prefix: str = "MatrixAgent") -> dict[str, Any]:
    tasks = {
        "api": f"{prefix}-API",
        "ad_poll": f"{prefix}-AdPoll",
    }
    rows = {key: _windows_task_status(name) for key, name in tasks.items()}
    installed = any(v.get("exists") for v in rows.values())
    return {
        "ok": True,
        "platform": "windows",
        "installed": installed,
        "tasks": rows,
        "install_hint": "powershell -ExecutionPolicy Bypass -File scripts/windows/install_service.ps1",
    }


def _systemd_unit_path(name: str = "ai-agent-matrix.service") -> Path:
    return project_root() / "deploy" / "systemd" / name


def systemd_autostart_status(*, unit: str = "ai-agent-matrix.service") -> dict[str, Any]:
    unit_path = _systemd_unit_path(unit)
    template_ready = unit_path.is_file()
    active = "unknown"
    enabled = "unknown"
    if platform.system().lower() == "linux" and template_ready:
        for cmd, key in (
            (["systemctl", "is-active", unit], "active"),
            (["systemctl", "is-enabled", unit], "enabled"),
        ):
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=8,
                    check=False,
                )
                val = (proc.stdout or proc.stderr or "").strip().lower()
                if key == "active":
                    active = val or "unknown"
                else:
                    enabled = val or "unknown"
            except Exception:
                pass
    return {
        "ok": template_ready,
        "platform": "linux",
        "unit_file": str(unit_path),
        "template_ready": template_ready,
        "active": active,
        "enabled": enabled,
        "install_hint": "sudo bash scripts/systemd_install.sh",
    }


def runtime_status() -> dict[str, Any]:
    sysname = platform.system().lower()
    health = probe_api_health()
    autostart: dict[str, Any]
    if sysname == "windows":
        autostart = windows_autostart_status()
    elif sysname == "linux":
        autostart = systemd_autostart_status()
    else:
        autostart = {"ok": False, "platform": sysname, "hint": "使用 Docker 或手动 python api_server.py"}

    workers = _worker_status()
    live_ready = bool(health.get("reachable")) and bool(health.get("ok"))
    return {
        "ok": True,
        "platform": sysname,
        "python": sys.version.split()[0],
        "project_root": str(project_root()),
        "api_health": health,
        "api_live": live_ready,
        "autostart": autostart,
        "workers": workers,
        "hints": {
            "start_api": "python api_server.py",
            "windows_service": "scripts/windows/install_service.ps1",
            "systemd_service": "scripts/systemd_install.sh",
            "docker_full": "python scripts/docker_up.py --stack full --build",
            "live_runbook": "python scripts/acceptance_live_runbook.py",
        },
    }
