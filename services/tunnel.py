"""公网隧道（ngrok / cloudflare）检测与 REVIEW_BASE_URL 辅助。"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any


def detect_tunnel_providers() -> dict[str, bool]:
    return {
        "ngrok": shutil.which("ngrok") is not None,
        "cloudflared": shutil.which("cloudflared") is not None,
    }


def review_callback_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/api/review/callback"


def fetch_ngrok_public_url(*, api_addr: str = "http://127.0.0.1:4040") -> str:
    try:
        req = urllib.request.Request(f"{api_addr.rstrip('/')}/api/tunnels", headers={"User-Agent": "matrix-tunnel/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for tunnel in data.get("tunnels") or []:
            url = str(tunnel.get("public_url") or "")
            if url.startswith("https://"):
                return url.rstrip("/")
        for tunnel in data.get("tunnels") or []:
            url = str(tunnel.get("public_url") or "")
            if url.startswith("http://"):
                return url.rstrip("/")
    except Exception:
        pass
    return ""


def parse_cloudflared_url(text: str) -> str:
    m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", text or "", re.I)
    return m.group(0).rstrip("/") if m else ""


def tunnel_status(*, port: int = 9200) -> dict[str, Any]:
    providers = detect_tunnel_providers()
    configured_base = (os.environ.get("REVIEW_BASE_URL") or "").strip().rstrip("/")
    ngrok_url = fetch_ngrok_public_url() if providers.get("ngrok") else ""
    public_url = ngrok_url or (configured_base if configured_base.startswith("https://") else "")
    is_local = configured_base.startswith("http://127.0.0.1") or configured_base.startswith("http://localhost")
    return {
        "ok": True,
        "port": port,
        "providers": providers,
        "review_base_url": configured_base or f"http://127.0.0.1:{port}",
        "callback_url": review_callback_url(configured_base or f"http://127.0.0.1:{port}"),
        "ngrok_public_url": ngrok_url,
        "public_reachable": bool(public_url and public_url.startswith("https://")),
        "needs_tunnel": is_local or not public_url,
        "setup_hint": (
            "本地 REVIEW_BASE_URL 飞书无法回调，请运行: python scripts/tunnel_up.py --provider ngrok"
            if is_local
            else "REVIEW_BASE_URL 已配置为公网或自定义域名"
        ),
    }


def start_ngrok_tunnel(*, port: int = 9200, block_until_ms: int = 8000) -> dict[str, Any]:
    if not detect_tunnel_providers().get("ngrok"):
        return {"ok": False, "error": "ngrok_not_installed", "hint": "https://ngrok.com/download"}
    try:
        subprocess.Popen(
            ["ngrok", "http", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        return {"ok": False, "error": "ngrok_start_failed", "detail": str(exc)[:200]}

    deadline = time.time() + block_until_ms / 1000.0
    public_url = ""
    while time.time() < deadline:
        public_url = fetch_ngrok_public_url()
        if public_url:
            break
        time.sleep(0.5)

    if not public_url:
        return {"ok": False, "error": "ngrok_url_timeout", "hint": "检查 ngrok 是否已登录: ngrok config add-authtoken ..."}

    return {
        "ok": True,
        "provider": "ngrok",
        "public_url": public_url,
        "review_base_url": public_url,
        "callback_url": review_callback_url(public_url),
        "env_line": f"REVIEW_BASE_URL={public_url}",
    }


def start_cloudflared_tunnel(*, port: int = 9200, block_until_ms: int = 15000) -> dict[str, Any]:
    if not detect_tunnel_providers().get("cloudflared"):
        return {"ok": False, "error": "cloudflared_not_installed", "hint": "https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/"}
    try:
        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        return {"ok": False, "error": "cloudflared_start_failed", "detail": str(exc)[:200]}

    public_url = ""
    deadline = time.time() + block_until_ms / 1000.0
    buf = ""
    while time.time() < deadline and not public_url:
        line = proc.stdout.readline() if proc.stdout else ""
        if line:
            buf += line
            public_url = parse_cloudflared_url(buf)
        elif proc.poll() is not None:
            break
        else:
            time.sleep(0.2)

    if not public_url:
        return {"ok": False, "error": "cloudflared_url_timeout", "log_tail": buf[-400:]}

    return {
        "ok": True,
        "provider": "cloudflared",
        "public_url": public_url,
        "review_base_url": public_url,
        "callback_url": review_callback_url(public_url),
        "env_line": f"REVIEW_BASE_URL={public_url}",
        "pid": proc.pid,
    }
