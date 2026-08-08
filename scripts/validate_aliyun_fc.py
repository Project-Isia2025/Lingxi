#!/usr/bin/env python
"""本地验证阿里云 FC handler（无需实际上云）。"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()


def _load_fc_handler():
    path = ROOT / "deploy" / "aliyun-fc" / "handler.py"
    spec = importlib.util.spec_from_file_location("lingxi_fc_handler", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    fc_mod = _load_fc_handler()
    event = {
        "rawPath": "/health",
        "requestContext": {"http": {"method": "GET"}},
        "headers": {"host": "localhost"},
        "body": "",
    }
    resp = fc_mod.handler(event, None)
    ok = int(resp.get("statusCode") or 0) == 200
    print(
        json.dumps(
            {
                "ok": ok,
                "statusCode": resp.get("statusCode"),
                "body_preview": str(resp.get("body"))[:120],
            },
            ensure_ascii=False,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
