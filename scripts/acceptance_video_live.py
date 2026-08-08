#!/usr/bin/env python
"""AI 视频 Provider 联调验收（默认 mock 烟测，--live 需真实 API Key）。

用法:
  python scripts/acceptance_video_live.py              # 凭证检查 + mock 成片
  python scripts/acceptance_video_live.py --provider avatar
  python scripts/acceptance_video_live.py --live --confirm --provider avatar
  python scripts/acceptance_video_live.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()


def _step(name: str, fn) -> dict[str, Any]:
    try:
        out = fn()
        ok = bool(out.get("ok", True)) if isinstance(out, dict) else bool(out)
        return {"step": name, "ok": ok, "result": out}
    except Exception as exc:
        return {"step": name, "ok": False, "error": str(exc)[:300]}


def run_video_acceptance(
    *,
    provider: str = "",
    live: bool = False,
    confirm: bool = False,
    script: str = "联调测试：A款面膜，15秒口播验收。",
) -> dict[str, Any]:
    from services.video_provider_status import all_providers_status, provider_status
    from services.video_providers.router import list_providers, produce_video

    steps: list[dict[str, Any]] = []
    summary = all_providers_status()
    steps.append(_step("providers_status", lambda: summary))

    targets = [provider.strip().lower()] if provider else list_providers()
    run_id = f"live-{uuid.uuid4().hex[:8]}"

    if live and not confirm:
        return {
            "ok": False,
            "error": "live_requires_confirm",
            "hint": "真实 API 调用可能产生费用，请追加 --confirm",
            "steps": steps,
        }

    for pid in targets:
        st = provider_status(pid)
        steps.append(_step(f"credentials_{pid}", lambda s=st: s))

        def _produce(p=pid, status=st) -> dict[str, Any]:
            if live and status.get("configured"):
                return produce_video(
                    provider=p,
                    script=script,
                    run_id=run_id,
                    source_video="",
                    image_path="",
                )

            with tempfile.TemporaryDirectory() as td:
                src = Path(td) / "mock_src.mp4"
                src.write_bytes(b"\x00\x00\x00\x20ftypmp42" + b"\x00" * 64)
                from unittest.mock import patch

                if status.get("configured") and not live:
                    # 有 Key 但 dry-run：强制 mock，避免误调用
                    with patch("services.video_providers.http_client.api_credentials", return_value=("", "")):
                        return produce_video(
                            provider=p,
                            script=script,
                            run_id=run_id,
                            source_video=str(src),
                        )
                return produce_video(
                    provider=p,
                    script=script,
                    run_id=run_id,
                    source_video=str(src),
                )

        steps.append(_step(f"produce_{pid}", _produce))

    passed = sum(1 for s in steps if s.get("ok"))
    live_used = live and any(
        s.get("result", {}).get("mode") == "api"
        for s in steps
        if str(s.get("step", "")).startswith("produce_")
    )
    return {
        "ok": passed == len(steps),
        "passed": passed,
        "total": len(steps),
        "live": live,
        "live_api_called": live_used,
        "configured_providers": summary.get("configured") or [],
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 视频 Provider 联调验收")
    parser.add_argument("--provider", default="", help="avatar | volc | kling，默认全部")
    parser.add_argument("--live", action="store_true", help="使用真实 API（需 Key）")
    parser.add_argument("--confirm", action="store_true", help="确认真实 API 可能产生费用")
    parser.add_argument("--script", default="联调测试：A款面膜，15秒口播验收。")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_video_acceptance(
        provider=args.provider,
        live=args.live,
        confirm=args.confirm,
        script=args.script,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        mode = "LIVE" if args.live else "DRY-RUN(mock)"
        print(f"视频 Provider 联调 [{mode}]: {report.get('passed', 0)}/{report.get('total', 0)} 通过")
        if report.get("configured_providers"):
            print(f"  已配置 Key: {', '.join(report['configured_providers'])}")
        for step in report.get("steps") or []:
            mark = "OK" if step.get("ok") else "FAIL"
            print(f"  [{mark}] {step['step']}")
            if not step.get("ok"):
                print(f"       {step.get('error') or step.get('result')}")
        if report.get("error"):
            print(f"  错误: {report['error']} — {report.get('hint', '')}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
