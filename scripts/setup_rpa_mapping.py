#!/usr/bin/env python
"""初始化影刀 RPA 字段映射文件。

用法:
  python scripts/setup_rpa_mapping.py
  python scripts/setup_rpa_mapping.py --force
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="覆盖已存在的映射文件")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    from services.rpa_ingest import init_field_mapping_file

    out = init_field_mapping_file(force=args.force)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if out.get("ok"):
            if out.get("created"):
                print(f"已创建: {out.get('path')}")
            else:
                print(f"已存在: {out.get('path')}（使用 --force 覆盖）")
        else:
            print(f"失败: {out.get('error')}")
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
