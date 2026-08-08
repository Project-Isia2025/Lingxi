#!/usr/bin/env python
"""公网隧道启动 — 为飞书回调暴露本地 API（ngrok / cloudflare）。

用法:
  python scripts/tunnel_up.py --check
  python scripts/tunnel_up.py --provider ngrok --port 9200
  python scripts/tunnel_up.py --provider cloudflare --port 9200
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()


def main() -> int:
    from services.tunnel import (
        detect_tunnel_providers,
        start_cloudflared_tunnel,
        start_ngrok_tunnel,
        tunnel_status,
    )

    parser = argparse.ArgumentParser(description="公网隧道（飞书回调 REVIEW_BASE_URL）")
    parser.add_argument("--check", action="store_true", help="检查隧道工具与当前状态")
    parser.add_argument("--provider", choices=["ngrok", "cloudflare"], default="ngrok")
    parser.add_argument("--port", type=int, default=9200)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.check:
        out = tunnel_status(port=args.port)
        out["providers_installed"] = detect_tunnel_providers()
        if args.json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            prov = out["providers_installed"]
            print("隧道工具:", ", ".join(k for k, v in prov.items() if v) or "无")
            print(f"REVIEW_BASE_URL: {out.get('review_base_url')}")
            print(f"回调 URL: {out.get('callback_url')}")
            print(f"需要隧道: {'是' if out.get('needs_tunnel') else '否'}")
            if out.get("ngrok_public_url"):
                print(f"ngrok 公网: {out['ngrok_public_url']}")
            print(out.get("setup_hint") or "")
        return 0

    if args.provider == "ngrok":
        out = start_ngrok_tunnel(port=args.port)
    else:
        out = start_cloudflared_tunnel(port=args.port)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if out.get("ok"):
            print(f"隧道已启动 [{out.get('provider')}]")
            print(f"公网 URL: {out.get('public_url')}")
            print(f"飞书回调: {out.get('callback_url')}")
            print(f"请写入 config/local.env:\n  {out.get('env_line')}")
            print("\n保持本窗口运行；另开终端启动 API: python api_server.py")
        else:
            print(f"启动失败: {out.get('error')}")
            if out.get("hint"):
                print(f"提示: {out['hint']}")
            if out.get("log_tail"):
                print(out["log_tail"])
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
