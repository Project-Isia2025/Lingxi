#!/usr/bin/env python
"""一键验收：pytest + 规范核查 + 切片 E2E + API 烟测 + Docker 校验。

用法:
  python scripts/acceptance_all.py
  python scripts/acceptance_all.py --quick          # 仅跑近期 phase 测试
  python scripts/acceptance_all.py --docker-live    # 含运行中容器健康探测
  python scripts/acceptance_all.py --skip-pytest    # 跳过单元测试
  python scripts/acceptance_all.py --json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()

StageStatus = Literal["PASS", "FAIL", "SKIP"]


@dataclass
class StageResult:
    name: str
    status: StageStatus
    detail: str = ""
    duration_sec: float = 0.0
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class AcceptanceAllReport:
    stages: list[StageResult] = field(default_factory=list)
    started_ts: float = 0.0
    finished_ts: float = 0.0

    def add(self, stage: StageResult) -> None:
        self.stages.append(stage)

    def summary(self) -> dict[str, Any]:
        counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
        for s in self.stages:
            counts[s.status] += 1
        required = [s for s in self.stages if s.status != "SKIP"]
        ok = all(s.status == "PASS" for s in required)
        return {
            "ok": ok,
            "passed": counts["PASS"],
            "failed": counts["FAIL"],
            "skipped": counts["SKIP"],
            "total": len(self.stages),
            "duration_sec": round(max(0.0, self.finished_ts - self.started_ts), 2),
        }


def _run_pytest(*, quick: bool) -> StageResult:
    t0 = time.time()
    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=no", "--disable-warnings"]
    if quick:
        cmd += [
            "tests/test_phase22_publish_dashboard.py",
            "tests/test_phase23_queue_ops_tenant.py",
            "tests/test_phase24_roi_org_resources.py",
            "tests/test_phase25_acceptance_all.py",
            "tests/test_phase26_video_live_ci.py",
            "tests/test_phase27_feishu_storage_wizard.py",
            "tests/test_phase28_tunnel_publish.py",
            "tests/test_phase29_publish_smoke_docker.py",
            "tests/test_phase30_deploy_submit.py",
            "tests/test_phase31_monitor_helm.py",
            "tests/test_phase32_runtime_runbook.py",
            "tests/test_phase33_runtime_dashboard.py",
            "tests/test_phase34_runtime_ws_org.py",
            "tests/test_phase35_org_webhook_runbook_alert.py",
        ]
    else:
        cmd.append("tests")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
        out_tail = (proc.stdout or proc.stderr or "")[-400:]
        ok = proc.returncode == 0
        return StageResult(
            name="pytest",
            status="PASS" if ok else "FAIL",
            detail=out_tail.strip() or f"exit={proc.returncode}",
            duration_sec=time.time() - t0,
            payload={"returncode": proc.returncode, "quick": quick},
        )
    except subprocess.TimeoutExpired:
        return StageResult(name="pytest", status="FAIL", detail="timeout 300s", duration_sec=time.time() - t0)
    except Exception as exc:
        return StageResult(name="pytest", status="FAIL", detail=str(exc)[:200], duration_sec=time.time() - t0)


def _run_spec() -> StageResult:
    t0 = time.time()
    try:
        from scripts.acceptance_verify import run_checks

        report = run_checks()
        summary = report.summary()
        ok = summary.get("FAIL", 0) == 0 and summary.get("MISSING", 0) == 0
        pass_rate = round(
            (summary["PASS"] + summary["PARTIAL"] * 0.5) / max(1, len(report.checks)) * 100,
            1,
        )
        return StageResult(
            name="spec_verify",
            status="PASS" if ok else "FAIL",
            detail=f"PASS={summary['PASS']} PARTIAL={summary['PARTIAL']} MISSING={summary['MISSING']} 就绪度={pass_rate}%",
            duration_sec=time.time() - t0,
            payload={"summary": summary, "checks_count": len(report.checks)},
        )
    except Exception as exc:
        return StageResult(name="spec_verify", status="FAIL", detail=str(exc)[:200], duration_sec=time.time() - t0)


def _run_slice_e2e() -> StageResult:
    t0 = time.time()
    try:
        from scripts.acceptance_slice_e2e import run_e2e

        out = run_e2e()
        ok = bool(out.get("ok"))
        return StageResult(
            name="slice_e2e",
            status="PASS" if ok else "FAIL",
            detail=f"{out.get('passed', 0)}/{out.get('total', 0)} 步骤通过",
            duration_sec=time.time() - t0,
            payload=out,
        )
    except Exception as exc:
        return StageResult(name="slice_e2e", status="FAIL", detail=str(exc)[:200], duration_sec=time.time() - t0)


def _run_api_smoke() -> StageResult:
    t0 = time.time()
    try:
        from scripts.acceptance_api_smoke import run_api_smoke

        out = run_api_smoke()
        ok = bool(out.get("ok"))
        return StageResult(
            name="api_smoke",
            status="PASS" if ok else "FAIL",
            detail=f"{out.get('passed', 0)}/{out.get('total', 0)} 端点通过",
            duration_sec=time.time() - t0,
            payload={"steps": out.get("steps")},
        )
    except Exception as exc:
        return StageResult(name="api_smoke", status="FAIL", detail=str(exc)[:200], duration_sec=time.time() - t0)


def _run_deploy_verify() -> StageResult:
    t0 = time.time()
    try:
        from scripts.acceptance_deploy_verify import run_deploy_verify

        out = run_deploy_verify()
        ok = bool(out.get("ok"))
        return StageResult(
            name="deploy_verify",
            status="PASS" if ok else "FAIL",
            detail=f"{out.get('passed', 0)}/{out.get('total', 0)} 部署模板检查",
            duration_sec=time.time() - t0,
        )
    except Exception as exc:
        return StageResult(name="deploy_verify", status="FAIL", detail=str(exc)[:200], duration_sec=time.time() - t0)


def _run_publish_smoke(*, live: bool = False) -> StageResult:
    t0 = time.time()
    try:
        from scripts.acceptance_publish_smoke import run_publish_smoke_acceptance

        out = run_publish_smoke_acceptance(live_probe=live)
        ok = bool(out.get("ok"))
        return StageResult(
            name="publish_smoke",
            status="PASS" if ok else "FAIL",
            detail=f"{out.get('passed', 0)}/{out.get('total', 0)} 步骤 | live={live}",
            duration_sec=time.time() - t0,
        )
    except Exception as exc:
        return StageResult(name="publish_smoke", status="FAIL", detail=str(exc)[:200], duration_sec=time.time() - t0)


def _run_publish_e2e() -> StageResult:
    t0 = time.time()
    try:
        from scripts.acceptance_publish_e2e import run_publish_e2e

        out = run_publish_e2e()
        ok = bool(out.get("ok"))
        return StageResult(
            name="publish_e2e",
            status="PASS" if ok else "FAIL",
            detail=f"{out.get('passed', 0)}/{out.get('total', 0)} 步骤 | ready={out.get('ready_platforms')}",
            duration_sec=time.time() - t0,
        )
    except Exception as exc:
        return StageResult(name="publish_e2e", status="FAIL", detail=str(exc)[:200], duration_sec=time.time() - t0)


def _run_feishu_e2e() -> StageResult:
    t0 = time.time()
    try:
        from scripts.acceptance_feishu_e2e import run_feishu_e2e

        out = run_feishu_e2e()
        ok = bool(out.get("ok"))
        return StageResult(
            name="feishu_e2e",
            status="PASS" if ok else "FAIL",
            detail=f"{out.get('passed', 0)}/{out.get('total', 0)} 步骤 | run={out.get('run_id')}",
            duration_sec=time.time() - t0,
        )
    except Exception as exc:
        return StageResult(name="feishu_e2e", status="FAIL", detail=str(exc)[:200], duration_sec=time.time() - t0)


def _run_video_live(*, live: bool = False) -> StageResult:
    t0 = time.time()
    try:
        from scripts.acceptance_video_live import run_video_acceptance

        out = run_video_acceptance(live=live, confirm=live)
        ok = bool(out.get("ok"))
        return StageResult(
            name="video_live",
            status="PASS" if ok else "FAIL",
            detail=f"{out.get('passed', 0)}/{out.get('total', 0)} 步骤 | configured={out.get('configured_providers')}",
            duration_sec=time.time() - t0,
            payload={"live": live, "configured": out.get("configured_providers")},
        )
    except Exception as exc:
        return StageResult(name="video_live", status="FAIL", detail=str(exc)[:200], duration_sec=time.time() - t0)


def _run_org_webhook_alert() -> StageResult:
    t0 = time.time()
    try:
        from scripts.acceptance_org_webhook_alert import run_org_webhook_acceptance

        out = run_org_webhook_acceptance()
        ok = bool(out.get("ok"))
        return StageResult(
            name="org_webhook_alert",
            status="PASS" if ok else "FAIL",
            detail=f"{out.get('passed', 0)}/{out.get('total', 0)} 检查",
            duration_sec=time.time() - t0,
        )
    except Exception as exc:
        return StageResult(name="org_webhook_alert", status="FAIL", detail=str(exc)[:200], duration_sec=time.time() - t0)


def _run_rpa_webhook() -> StageResult:
    t0 = time.time()
    try:
        from scripts.acceptance_rpa_webhook import run_rpa_webhook_acceptance

        out = run_rpa_webhook_acceptance()
        ok = bool(out.get("ok"))
        return StageResult(
            name="rpa_webhook",
            status="PASS" if ok else "FAIL",
            detail=f"{out.get('passed', 0)}/{out.get('total', 0)} 检查",
            duration_sec=time.time() - t0,
        )
    except Exception as exc:
        return StageResult(name="rpa_webhook", status="FAIL", detail=str(exc)[:200], duration_sec=time.time() - t0)


def _run_runtime_ws_org() -> StageResult:
    t0 = time.time()
    try:
        from scripts.acceptance_runtime_ws_org import run_runtime_ws_org_acceptance

        out = run_runtime_ws_org_acceptance()
        ok = bool(out.get("ok"))
        return StageResult(
            name="runtime_ws_org",
            status="PASS" if ok else "FAIL",
            detail=f"{out.get('passed', 0)}/{out.get('total', 0)} 检查",
            duration_sec=time.time() - t0,
        )
    except Exception as exc:
        return StageResult(name="runtime_ws_org", status="FAIL", detail=str(exc)[:200], duration_sec=time.time() - t0)


def _run_runtime_dashboard() -> StageResult:
    t0 = time.time()
    try:
        from scripts.acceptance_runtime_dashboard import run_runtime_dashboard_acceptance

        out = run_runtime_dashboard_acceptance()
        ok = bool(out.get("ok"))
        return StageResult(
            name="runtime_dashboard",
            status="PASS" if ok else "FAIL",
            detail=f"{out.get('passed', 0)}/{out.get('total', 0)} 检查",
            duration_sec=time.time() - t0,
        )
    except Exception as exc:
        return StageResult(name="runtime_dashboard", status="FAIL", detail=str(exc)[:200], duration_sec=time.time() - t0)


def _run_live_runbook(*, live: bool = False) -> StageResult:
    t0 = time.time()
    try:
        from services.live_runbook import build_live_runbook

        out = build_live_runbook(live=live)
        ok = bool(out.get("ok"))
        return StageResult(
            name="live_runbook",
            status="PASS" if ok else "FAIL",
            detail=f"{out.get('passed', 0)}/{out.get('total', 0)} 步骤 | live={live}",
            duration_sec=time.time() - t0,
        )
    except Exception as exc:
        return StageResult(name="live_runbook", status="FAIL", detail=str(exc)[:200], duration_sec=time.time() - t0)


def _run_monitor_e2e() -> StageResult:
    t0 = time.time()
    try:
        from scripts.acceptance_monitor_e2e import run_monitor_e2e

        out = run_monitor_e2e()
        ok = bool(out.get("ok"))
        return StageResult(
            name="monitor_e2e",
            status="PASS" if ok else "FAIL",
            detail=f"{out.get('passed', 0)}/{out.get('total', 0)} 步骤 | run={out.get('run_id')}",
            duration_sec=time.time() - t0,
        )
    except Exception as exc:
        return StageResult(name="monitor_e2e", status="FAIL", detail=str(exc)[:200], duration_sec=time.time() - t0)


def _run_docker_smoke(*, live: bool) -> StageResult:
    t0 = time.time()
    try:
        from scripts.acceptance_docker_smoke import run_docker_smoke

        out = run_docker_smoke(live=live)
        if out.get("skipped"):
            return StageResult(
                name="docker_smoke",
                status="SKIP",
                detail=out.get("message") or "docker 不可用",
                duration_sec=time.time() - t0,
            )
        ok = bool(out.get("ok"))
        return StageResult(
            name="docker_smoke",
            status="PASS" if ok else "FAIL",
            detail=f"{out.get('passed', 0)}/{out.get('total', 0)} 检查通过",
            duration_sec=time.time() - t0,
            payload=out,
        )
    except Exception as exc:
        return StageResult(name="docker_smoke", status="FAIL", detail=str(exc)[:200], duration_sec=time.time() - t0)


def run_acceptance_all(
    *,
    skip_pytest: bool = False,
    skip_spec: bool = False,
    skip_e2e: bool = False,
    skip_api: bool = False,
    skip_video: bool = False,
    skip_feishu: bool = False,
    skip_publish: bool = False,
    skip_publish_smoke: bool = False,
    skip_monitor: bool = False,
    skip_live_runbook: bool = False,
    skip_runtime_dashboard: bool = False,
    skip_runtime_ws_org: bool = False,
    skip_org_webhook: bool = False,
    skip_deploy: bool = False,
    skip_docker: bool = False,
    quick: bool = False,
    docker_live: bool = False,
    video_live: bool = False,
    publish_smoke_live: bool = False,
    live_runbook_live: bool = False,
) -> AcceptanceAllReport:
    report = AcceptanceAllReport(started_ts=time.time())

    if skip_pytest:
        report.add(StageResult(name="pytest", status="SKIP", detail="--skip-pytest"))
    else:
        report.add(_run_pytest(quick=quick))

    if skip_spec:
        report.add(StageResult(name="spec_verify", status="SKIP", detail="--skip-spec"))
    else:
        report.add(_run_spec())

    if skip_e2e:
        report.add(StageResult(name="slice_e2e", status="SKIP", detail="--skip-e2e"))
    else:
        report.add(_run_slice_e2e())

    if skip_api:
        report.add(StageResult(name="api_smoke", status="SKIP", detail="--skip-api"))
    else:
        report.add(_run_api_smoke())

    if skip_video:
        report.add(StageResult(name="video_live", status="SKIP", detail="--skip-video"))
    else:
        report.add(_run_video_live(live=video_live))

    if skip_feishu:
        report.add(StageResult(name="feishu_e2e", status="SKIP", detail="--skip-feishu"))
    else:
        report.add(_run_feishu_e2e())

    if skip_publish:
        report.add(StageResult(name="publish_e2e", status="SKIP", detail="--skip-publish"))
    else:
        report.add(_run_publish_e2e())

    if skip_publish_smoke:
        report.add(StageResult(name="publish_smoke", status="SKIP", detail="--skip-publish-smoke"))
    else:
        report.add(_run_publish_smoke(live=publish_smoke_live))

    if skip_monitor:
        report.add(StageResult(name="monitor_e2e", status="SKIP", detail="--skip-monitor"))
    else:
        report.add(_run_monitor_e2e())

    if skip_live_runbook:
        report.add(StageResult(name="live_runbook", status="SKIP", detail="--skip-live-runbook"))
    else:
        report.add(_run_live_runbook(live=live_runbook_live))

    if skip_runtime_dashboard:
        report.add(StageResult(name="runtime_dashboard", status="SKIP", detail="--skip-runtime-dashboard"))
    else:
        report.add(_run_runtime_dashboard())

    if skip_runtime_ws_org:
        report.add(StageResult(name="runtime_ws_org", status="SKIP", detail="--skip-runtime-ws-org"))
    else:
        report.add(_run_runtime_ws_org())

    if skip_org_webhook:
        report.add(StageResult(name="org_webhook_alert", status="SKIP", detail="--skip-org-webhook"))
    else:
        report.add(_run_org_webhook_alert())

    report.add(_run_rpa_webhook())

    if skip_deploy:
        report.add(StageResult(name="deploy_verify", status="SKIP", detail="--skip-deploy"))
    else:
        report.add(_run_deploy_verify())

    if skip_docker:
        report.add(StageResult(name="docker_smoke", status="SKIP", detail="--skip-docker"))
    else:
        report.add(_run_docker_smoke(live=docker_live))

    report.finished_ts = time.time()
    return report


def print_report(report: AcceptanceAllReport) -> None:
    summary = report.summary()
    print("=" * 72)
    print("  五层 AI 智能体矩阵 — 一键验收报告")
    print("=" * 72)
    for stage in report.stages:
        icon = {"PASS": "[OK]", "FAIL": "[!]", "SKIP": "[-]"}.get(stage.status, "?")
        print(f"  {icon} {stage.name:14} {stage.status:4}  ({stage.duration_sec:.1f}s)  {stage.detail}")
    print("-" * 72)
    print(
        f"  阶段 {summary['total']} 项 | 通过 {summary['passed']} | 失败 {summary['failed']} | "
        f"跳过 {summary['skipped']} | 耗时 {summary['duration_sec']}s"
    )
    print(f"  结论: {'全部通过' if summary['ok'] else '存在失败项，请查看上方明细'}")
    print("=" * 72)


def main() -> int:
    parser = argparse.ArgumentParser(description="一键验收（pytest + 规范 + E2E + API + Docker）")
    parser.add_argument("--quick", action="store_true", help="pytest 仅跑 phase22-35")
    parser.add_argument("--skip-pytest", action="store_true")
    parser.add_argument("--skip-spec", action="store_true")
    parser.add_argument("--skip-e2e", action="store_true")
    parser.add_argument("--skip-api", action="store_true")
    parser.add_argument("--skip-video", action="store_true")
    parser.add_argument("--skip-feishu", action="store_true")
    parser.add_argument("--skip-publish", action="store_true")
    parser.add_argument("--skip-publish-smoke", action="store_true")
    parser.add_argument("--skip-monitor", action="store_true")
    parser.add_argument("--skip-live-runbook", action="store_true")
    parser.add_argument("--skip-runtime-dashboard", action="store_true")
    parser.add_argument("--skip-runtime-ws-org", action="store_true")
    parser.add_argument("--skip-org-webhook", action="store_true")
    parser.add_argument("--skip-deploy", action="store_true")
    parser.add_argument("--skip-docker", action="store_true")
    parser.add_argument("--docker-live", action="store_true", help="Docker 阶段探测运行中 /api/health")
    parser.add_argument("--video-live", action="store_true", help="视频联调使用真实 API（需 Key + 费用）")
    parser.add_argument("--publish-smoke-live", action="store_true", help="Playwright 上传页真实探测（需登录态）")
    parser.add_argument("--live-runbook-live", action="store_true", help="Runbook 含真实上传页探测")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_acceptance_all(
        skip_pytest=args.skip_pytest,
        skip_spec=args.skip_spec,
        skip_e2e=args.skip_e2e,
        skip_api=args.skip_api,
        skip_video=args.skip_video,
        skip_feishu=args.skip_feishu,
        skip_publish=args.skip_publish,
        skip_publish_smoke=args.skip_publish_smoke,
        skip_monitor=args.skip_monitor,
        skip_live_runbook=args.skip_live_runbook,
        skip_runtime_dashboard=args.skip_runtime_dashboard,
        skip_runtime_ws_org=args.skip_runtime_ws_org,
        skip_org_webhook=args.skip_org_webhook,
        skip_deploy=args.skip_deploy,
        skip_docker=args.skip_docker,
        quick=args.quick,
        docker_live=args.docker_live,
        video_live=args.video_live,
        publish_smoke_live=args.publish_smoke_live,
        live_runbook_live=args.live_runbook_live,
    )
    summary = report.summary()

    if args.json:
        payload = {
            "summary": summary,
            "stages": [asdict(s) for s in report.stages],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_report(report)

    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
