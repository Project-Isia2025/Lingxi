#!/usr/bin/env python
"""Docker 一键启动辅助脚本。"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ensure_path() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import bootstrap

    bootstrap.ensure_paths()


def _build_compose_cmd(*, profiles: list[str], action: str, build: bool) -> list[str]:
    cmd = ["docker", "compose", "-f", str(ROOT / "docker-compose.yml")]
    for prof in profiles:
        cmd += ["--profile", prof]
    if action == "up":
        cmd += ["up", "-d"]
        if build:
            cmd.append("--build")
    elif action == "build":
        cmd += ["build"]
    elif action == "down":
        cmd += ["down"]
    else:
        cmd += ["logs", "-f"]
    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(description="Docker Compose 启动矩阵 API")
    parser.add_argument("action", choices=["up", "down", "build", "logs"], nargs="?", default="up")
    parser.add_argument("--build", action="store_true", help="up 时强制 rebuild")
    parser.add_argument("--profile", default="", help="单个 profile：playwright | tunnel")
    parser.add_argument(
        "--stack",
        default="",
        help="预设栈：default | playwright | tunnel | full（full=API+Playwright+隧道）",
    )
    args = parser.parse_args()

    env_example = ROOT / "config" / "local.env.example"
    env_file = ROOT / "config" / "local.env"
    if not env_file.is_file() and env_example.is_file():
        env_file.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"已复制 {env_example.name} -> local.env", file=sys.stderr)

    _ensure_path()
    from services.compose_profiles import resolve_profiles

    if args.stack:
        profiles = resolve_profiles(args.stack)
    elif args.profile:
        profiles = resolve_profiles(args.profile)
    else:
        profiles = []

    cmd = _build_compose_cmd(profiles=profiles, action=args.action, build=args.build)
    print(" ".join(cmd), file=sys.stderr)
    if args.stack == "full" and args.action == "up":
        print("提示: 查看隧道公网 URL → docker logs ai-agent-matrix-tunnel", file=sys.stderr)
        print("      将 URL 写入 REVIEW_BASE_URL 供飞书回调", file=sys.stderr)
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
