#!/usr/bin/env python
"""Docker Compose 配置校验 + 可选运行中容器健康检查。

用法:
  python scripts/acceptance_docker_smoke.py
  python scripts/acceptance_docker_smoke.py --live   # 容器已启动时探测 /api/health
  python scripts/acceptance_docker_smoke.py --json
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "docker-compose.yml"


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 120) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd or ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-500:],
            "stderr": (proc.stderr or "")[-500:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _http_health(url: str, timeout: float = 5.0) -> dict[str, Any]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "acceptance-docker-smoke/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw)
            except Exception:
                body = {"raw": raw[:200]}
            return {"ok": resp.status == 200 and bool(body.get("ok", True)), "status": resp.status, "body": body}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "error": str(exc)[:200]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def run_docker_smoke(*, live: bool = False, port: int = 9100) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []

    docker_ok = shutil.which("docker") is not None
    steps.append({"step": "docker_cli", "ok": docker_ok, "skipped": not docker_ok})
    if not docker_ok:
        return {
            "ok": True,
            "skipped": True,
            "message": "docker 未安装，跳过 Docker 烟测",
            "passed": 0,
            "total": 0,
            "steps": steps,
        }

    files_ok = COMPOSE.is_file() and (ROOT / "Dockerfile").is_file()
    steps.append({"step": "compose_files", "ok": files_ok})
    if not files_ok:
        return {"ok": False, "passed": 0, "total": len(steps), "steps": steps}

    cfg = _run(["docker", "compose", "-f", str(COMPOSE), "config"])
    steps.append({"step": "compose_config", "ok": cfg.get("ok"), "detail": cfg})

    if live:
        health = _http_health(f"http://127.0.0.1:{port}/api/health")
        steps.append({"step": "live_health", "ok": health.get("ok"), "detail": health})
    else:
        ps = _run(["docker", "ps", "--filter", "name=ai-agent-matrix", "--format", "{{.Names}}"])
        running = "ai-agent-matrix" in (ps.get("stdout") or "")
        steps.append({
            "step": "container_running",
            "ok": True,
            "skipped": not running,
            "detail": "容器未运行（正常）；使用 --live 在启动后探测",
        })

    passed = sum(1 for s in steps if s.get("ok"))
    required = [s for s in steps if not s.get("skipped")]
    ok = all(s.get("ok") for s in required)
    return {
        "ok": ok,
        "skipped": False,
        "passed": passed,
        "total": len(steps),
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Docker 烟测")
    parser.add_argument("--live", action="store_true", help="探测运行中 API /api/health")
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_docker_smoke(live=args.live, port=args.port)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        if report.get("skipped"):
            print(report.get("message") or "Docker 烟测已跳过")
        else:
            print(f"Docker 烟测: {report['passed']}/{report['total']} 通过")
            for step in report["steps"]:
                mark = "OK" if step.get("ok") else ("SKIP" if step.get("skipped") else "FAIL")
                print(f"  [{mark}] {step['step']}")
    if report.get("skipped"):
        return 0
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
