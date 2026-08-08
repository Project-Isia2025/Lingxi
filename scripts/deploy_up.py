#!/usr/bin/env python
"""生产部署启动 — 叠加 deploy/docker-compose.prod.yml。

用法:
  python scripts/deploy_up.py --check
  python scripts/deploy_up.py --stack prod --build
  python scripts/deploy_up.py --stack prod-full --build
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ensure_path() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import bootstrap

    bootstrap.ensure_paths()


def _profiles_for_stack(stack: str) -> list[str]:
    key = (stack or "prod").strip().lower()
    if key in ("prod-full", "full-prod", "production-full"):
        return ["playwright", "tunnel"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="生产 Docker Compose 部署")
    parser.add_argument("action", choices=["up", "down", "build", "config"], nargs="?", default="up")
    parser.add_argument("--stack", default="prod", help="prod | prod-full")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    _ensure_path()
    from services.deploy_status import deploy_manifest_status, validate_k8s_yaml

    if args.check:
        out = {
            "manifest": deploy_manifest_status(),
            "k8s_yaml": validate_k8s_yaml(),
        }
        if args.json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            m = out["manifest"]
            print(f"部署目录: {m.get('deploy_dir')}")
            print(f"Docker prod: {'OK' if m.get('docker_prod_ready') else 'MISSING'}")
            print(f"K8s: {'OK' if m.get('k8s_ready') else 'MISSING'}")
            print(f"K8s YAML: {'OK' if out['k8s_yaml'].get('ok') else out['k8s_yaml'].get('issues')}")
            for k, v in (m.get("hints") or {}).items():
                print(f"  {k}: {v}")
        return 0 if out["manifest"].get("ok") else 1

    base = ROOT / "docker-compose.yml"
    prod = ROOT / "deploy" / "docker-compose.prod.yml"
    if not base.is_file() or not prod.is_file():
        print("缺少 compose 文件", file=sys.stderr)
        return 1

    profiles = _profiles_for_stack(args.stack)
    cmd = [
        "docker", "compose",
        "-f", str(base),
        "-f", str(prod),
    ]
    for p in profiles:
        cmd += ["--profile", p]

    if args.action == "up":
        cmd += ["up", "-d"]
        if args.build:
            cmd.append("--build")
    elif args.action == "build":
        cmd += ["build"]
    elif args.action == "down":
        cmd += ["down"]
    else:
        cmd += ["config"]

    print(" ".join(cmd), file=sys.stderr)
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
