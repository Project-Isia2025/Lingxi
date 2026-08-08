#!/usr/bin/env python
"""Playwright 登录态导出向导 — 检查 / 导出抖音·小红书·视频号登录态。

用法:
  python scripts/export_storage_wizard.py --check
  python scripts/export_storage_wizard.py --export douyin_creator
  python scripts/export_storage_wizard.py --export-all-missing
  python scripts/export_storage_wizard.py --list
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


def _print_check_report(summary: dict) -> None:
    print("登录态检查报告")
    print("-" * 60)
    for row in summary.get("targets") or []:
        mark = "OK" if row.get("ready") else "MISSING"
        cookies = row.get("cookies", 0)
        print(f"  [{mark}] {row['id']:18} {row['label']}")
        print(f"         路径: {row['path']}")
        print(f"         env:  {row['env']}={row['path']}")
        if row.get("ready"):
            print(f"         cookies={cookies} size={row.get('size_bytes', 0)}B")
    print("-" * 60)
    print(f"  就绪: {', '.join(summary.get('ready') or []) or '无'}")
    print(f"  缺失: {', '.join(summary.get('missing') or []) or '无'}")


def main() -> int:
    from services.storage_state_wizard import (
        STORAGE_TARGETS,
        all_storage_status,
        export_storage_state,
    )

    parser = argparse.ArgumentParser(description="Playwright 登录态导出向导")
    parser.add_argument("--check", action="store_true", help="检查现有登录态文件")
    parser.add_argument("--list", action="store_true", help="列出所有导出目标")
    parser.add_argument("--export", default="", help="导出指定 target，如 douyin_creator")
    parser.add_argument("--export-all-missing", action="store_true", help="依次导出所有缺失项（交互）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.list:
        rows = [{"id": k, **v} for k, v in STORAGE_TARGETS.items()]
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            for row in rows:
                print(f"{row['id']:18} [{row['purpose']}] {row['label']}")
                print(f"  URL: {row['url']}")
                print(f"  ENV: {row['env']}")
        return 0

    if args.check or (not args.export and not args.export_all_missing):
        summary = all_storage_status()
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            _print_check_report(summary)
        if not args.export and not args.export_all_missing:
            return 0

    if args.export:
        if args.export not in STORAGE_TARGETS:
            print(f"未知 target: {args.export}，可用: {', '.join(STORAGE_TARGETS)}")
            return 1
        out = export_storage_state(target_id=args.export)
        if args.json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            if out.get("ok"):
                print(f"已导出 {args.export} -> {out['path']}")
                print(f"请设置: {out['env_line']}")
            else:
                print(f"导出失败: {out}")
        return 0 if out.get("ok") else 1

    if args.export_all_missing:
        summary = all_storage_status()
        missing = summary.get("missing") or []
        if not missing:
            print("所有登录态均已就绪")
            return 0
        for tid in missing:
            print(f"\n>>> 导出缺失项: {tid} ({STORAGE_TARGETS[tid]['label']})")
            out = export_storage_state(target_id=tid)
            if not out.get("ok"):
                print(f"失败: {out}")
                return 1
            print(f"完成: {out['env_line']}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
