#!/usr/bin/env python
"""数据库迁移 CLI（Alembic + schema_meta）。

用法:
  python scripts/migrate.py status
  python scripts/migrate.py upgrade
  python scripts/migrate.py stamp 001_baseline
  python scripts/migrate.py revision -m "add foo column"
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
    parser = argparse.ArgumentParser(description="Lingxi Engine DB migrations")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Show migration status")
    sub.add_parser("upgrade", help="Upgrade to head")
    stamp_p = sub.add_parser("stamp", help="Stamp revision without running migrations")
    stamp_p.add_argument("revision", help="Target revision id")

    rev_p = sub.add_parser("revision", help="Create new empty revision")
    rev_p.add_argument("-m", "--message", required=True, help="Migration message")

    args = parser.parse_args()

    if args.cmd == "status":
        from core.migrate import migration_status

        out = migration_status()
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "upgrade":
        from core.migrate import ensure_migrated

        out = ensure_migrated()
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out.get("ok") else 1

    if args.cmd == "stamp":
        from core.migrate import stamp_revision

        stamp_revision(args.revision)
        print(json.dumps({"ok": True, "revision": args.revision}, ensure_ascii=False))
        return 0

    if args.cmd == "revision":
        from alembic import command

        from core.migrate import _alembic_config

        command.revision(_alembic_config(), message=args.message, autogenerate=False)
        print(json.dumps({"ok": True, "message": args.message}, ensure_ascii=False))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
