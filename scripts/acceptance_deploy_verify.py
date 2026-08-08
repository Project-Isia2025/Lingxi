#!/usr/bin/env python
"""部署模板验收（Docker prod + K8s manifest 静态校验）。

用法:
  python scripts/acceptance_deploy_verify.py
  python scripts/acceptance_deploy_verify.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


def run_deploy_verify() -> dict[str, Any]:
    from services.compose_profiles import compose_status
    from services.deploy_status import deploy_manifest_status, deploy_root, validate_helm_chart, validate_k8s_yaml
    from services.publish_smoke import probe_publish_upload

    steps: list[dict[str, Any]] = []

    manifest = deploy_manifest_status()
    steps.append({"step": "deploy_manifest", "ok": manifest.get("ok"), "result": manifest})

    k8s = validate_k8s_yaml()
    steps.append({"step": "k8s_yaml", "ok": k8s.get("ok"), "result": k8s})

    helm = validate_helm_chart()
    steps.append({"step": "helm_chart", "ok": helm.get("ok"), "result": helm})

    systemd_unit = deploy_root() / "systemd" / "ai-agent-matrix.service"
    steps.append({
        "step": "systemd_unit",
        "ok": systemd_unit.is_file(),
        "result": {"path": str(systemd_unit), "exists": systemd_unit.is_file()},
    })

    compose = compose_status()
    steps.append({"step": "compose_profiles", "ok": compose.get("ok"), "result": compose})

    submit_guard = probe_publish_upload(platform="douyin", submit=True, confirm=False)
    steps.append({
        "step": "submit_requires_confirm",
        "ok": submit_guard.get("error") == "submit_requires_confirm",
        "result": submit_guard,
    })

    passed = sum(1 for s in steps if s.get("ok"))
    return {"ok": passed == len(steps), "passed": passed, "total": len(steps), "steps": steps}


def main() -> int:
    parser = argparse.ArgumentParser(description="部署模板验收")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_deploy_verify()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"部署验收: {report.get('passed', 0)}/{report.get('total', 0)} 通过")
        for step in report.get("steps") or []:
            mark = "OK" if step.get("ok") else "FAIL"
            print(f"  [{mark}] {step['step']}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
