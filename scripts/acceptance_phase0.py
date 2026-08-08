"""Phase 0 基础设施验收脚本。

对照开发指南 3.3 验收标准:
  - docker-compose up 一键启动所有基础设施
  - PostgreSQL / Redis / Qdrant / MinIO 均可连接
  - Prometheus 能采集到各服务指标
  - Celery worker 能正常消费任务

用法:
  python scripts/acceptance_phase0.py              # 静态检查 + 可选连通性
  python scripts/acceptance_phase0.py --live       # 探测本机运行中的服务
  python scripts/acceptance_phase0.py --docker-up  # 启动 infra compose 后验收
  python scripts/acceptance_phase0.py --json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()

Status = Literal["PASS", "FAIL", "SKIP"]


@dataclass
class Phase0Check:
    id: str
    requirement: str
    status: Status
    evidence: str = ""
    detail: str = ""


@dataclass
class Phase0Report:
    checks: list[Phase0Check] = field(default_factory=list)

    def add(self, **kwargs) -> None:
        self.checks.append(Phase0Check(**kwargs))

    def summary(self) -> dict[str, int]:
        out = {"PASS": 0, "FAIL": 0, "SKIP": 0}
        for c in self.checks:
            out[c.status] += 1
        return out


def _file_ok(path: str) -> bool:
    return (ROOT / path).is_file()


def _compose_has_services() -> bool:
    for name in ("docker-compose.yml", "docker-compose.infra.yml"):
        text = (ROOT / name).read_text(encoding="utf-8")
        required = ("postgres", "redis", "qdrant", "minio", "prometheus", "grafana")
        if all(s in text for s in required):
            return True
    return False


def _run_compose_up() -> tuple[bool, str]:
    cmd = ["docker", "compose", "-f", "docker-compose.infra.yml", "up", "-d"]
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            return False, proc.stderr or proc.stdout
        time.sleep(15)
        return True, "compose up ok"
    except FileNotFoundError:
        return False, "docker 未安装"
    except subprocess.TimeoutExpired:
        return False, "docker compose 超时"


async def _live_checks(include_worker: bool) -> Phase0Report:
    from infra.health import check_all, check_prometheus, run_celery_task_sync

    r = Phase0Report()
    report = await check_all(include_worker=include_worker)

    svc_map = {c["service"]: c for c in report["checks"]}
    for svc, label in (
        ("postgres", "PostgreSQL 可连接"),
        ("redis", "Redis 可连接"),
        ("qdrant", "Qdrant 可连接"),
        ("minio", "MinIO 可连接"),
        ("celery_broker", "Celery Broker 可连接"),
    ):
        c = svc_map.get(svc, {})
        r.add(
            id=f"live-{svc}",
            requirement=label,
            status="PASS" if c.get("ok") else "FAIL",
            evidence=str(c),
        )

    prom = await check_prometheus()
    r.add(
        id="live-prometheus",
        requirement="Prometheus 可采集指标",
        status="PASS" if prom.get("ok") else "FAIL",
        evidence=str(prom),
    )

    if include_worker:
        task = run_celery_task_sync()
        r.add(
            id="live-celery-task",
            requirement="Celery worker 消费任务",
            status="PASS" if task.get("ok") else "FAIL",
            evidence=str(task),
        )
    else:
        r.add(
            id="live-celery-task",
            requirement="Celery worker 消费任务",
            status="SKIP",
            evidence="未启用 --worker 探测",
        )

    return r


def run_static_checks() -> Phase0Report:
    r = Phase0Report()

    r.add(
        id="0.1",
        requirement="docker-compose 定义基础设施服务",
        status="PASS" if _compose_has_services() else "FAIL",
        evidence="docker-compose.yml + docker-compose.infra.yml",
    )
    for fid, req, mod in (
        ("0.2", "infra/database.py PostgreSQL", "infra/database.py"),
        ("0.3", "infra/redis_client.py", "infra/redis_client.py"),
        ("0.4", "infra/message_bus.py", "infra/message_bus.py"),
        ("0.5", "infra/task_queue.py Celery", "infra/task_queue.py"),
        ("0.6", "infra/object_storage.py MinIO", "infra/object_storage.py"),
        ("0.7", "infra/health.py 连通性探测", "infra/health.py"),
        ("0.8", "deploy/prometheus.yml", "deploy/prometheus.yml"),
        ("0.9", "deploy/sql/init.sql", "deploy/sql/init.sql"),
    ):
        r.add(id=fid, requirement=req, status="PASS" if _file_ok(mod) else "FAIL")

    try:
        from infra.database import Base, SessionLocal, engine
        from infra.message_bus import MessageBus
        from infra.redis_client import redis_client
        from infra.task_queue import celery_app, health_check

        ok = all(
            [
                Base is not None,
                engine is not None,
                SessionLocal is not None,
                redis_client is not None,
                MessageBus is not None,
                celery_app.main == "commerce_agent",
                callable(health_check),
            ]
        )
        r.add(id="0.10", requirement="基础设施模块可导入", status="PASS" if ok else "FAIL")
    except Exception as exc:
        r.add(id="0.10", requirement="基础设施模块可导入", status="FAIL", detail=str(exc))

    return r


async def main_async(args: argparse.Namespace) -> int:
    report = run_static_checks()

    if args.docker_up:
        ok, msg = _run_compose_up()
        report.add(
            id="docker-up",
            requirement="docker compose up 启动基础设施",
            status="PASS" if ok else "FAIL",
            evidence=msg,
        )
        if not ok:
            _print_report(report, args.json)
            return 1

    if args.live or args.docker_up:
        live = await _live_checks(include_worker=args.worker)
        report.checks.extend(live.checks)
    else:
        report.add(
            id="live-skipped",
            requirement="连通性探测（需 --live 或 --docker-up）",
            status="SKIP",
            evidence="python scripts/acceptance_phase0.py --live",
        )

    _print_report(report, args.json)
    summary = report.summary()
    return 0 if summary["FAIL"] == 0 else 1


def _print_report(report: Phase0Report, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"summary": report.summary(), "checks": [asdict(c) for c in report.checks]}, ensure_ascii=False, indent=2))
        return
    print("=" * 60)
    print("Phase 0 基础设施验收")
    print("=" * 60)
    for c in report.checks:
        mark = {"PASS": "OK", "FAIL": "X", "SKIP": "-"}[c.status]
        print(f"[{mark}] {c.id}: {c.requirement}")
        if c.detail:
            print(f"     {c.detail}")
    print("-" * 60)
    s = report.summary()
    print(f"PASS={s['PASS']} FAIL={s['FAIL']} SKIP={s['SKIP']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0 基础设施验收")
    parser.add_argument("--live", action="store_true", help="探测本机已运行的基础设施")
    parser.add_argument("--docker-up", action="store_true", help="docker compose up 后验收")
    parser.add_argument("--worker", action="store_true", help="同时验证 Celery worker 消费")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
