"""多智能体系统开发指南 — 严格验收脚本。

用法:
  python scripts/acceptance_guide.py
  python scripts/acceptance_guide.py --json
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()

Status = Literal["PASS", "PARTIAL", "FAIL", "MISSING"]


@dataclass
class CheckResult:
    phase: str
    id: str
    requirement: str
    status: Status
    evidence: str = ""


@dataclass
class GuideReport:
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, **kwargs) -> None:
        self.checks.append(CheckResult(**kwargs))

    def summary(self) -> dict[str, int]:
        out = {"PASS": 0, "PARTIAL": 0, "FAIL": 0, "MISSING": 0}
        for c in self.checks:
            out[c.status] += 1
        return out


def _import(path: str) -> bool:
    try:
        importlib.import_module(path)
        return True
    except Exception:
        return False


def _file_exists(rel: str) -> bool:
    return (ROOT / rel).is_file()


def run_checks() -> GuideReport:
    r = GuideReport()

    # Phase 0
    r.add(phase="0", id="0.1", requirement="docker-compose 基础设施服务", status="PASS" if _file_exists("docker-compose.yml") else "FAIL", evidence="postgres/redis/qdrant/minio/prometheus/grafana")
    r.add(phase="0", id="0.2", requirement="infra/database.py PostgreSQL", status="PASS" if _import("infra.database") else "FAIL")
    r.add(phase="0", id="0.3", requirement="infra/redis_client.py + MessageBus", status="PASS" if _import("infra.redis_client") else "FAIL")
    r.add(phase="0", id="0.4", requirement="infra/task_queue.py Celery", status="PASS" if _import("infra.task_queue") else "FAIL")
    r.add(phase="0", id="0.5", requirement="infra/object_storage.py MinIO", status="PASS" if _import("infra.object_storage") else "FAIL")
    r.add(phase="0", id="0.6", requirement="deploy/prometheus.yml", status="PASS" if _file_exists("deploy/prometheus.yml") else "FAIL")

    # Phase 1
    r.add(phase="1", id="1.1", requirement="memory/vector_store.py", status="PASS" if _import("memory.vector_store") else "FAIL")
    r.add(phase="1", id="1.2", requirement="memory/banned_words.py", status="PASS" if _import("memory.banned_words") else "FAIL")
    r.add(phase="1", id="1.3", requirement="memory/sop_store.py", status="PASS" if _import("memory.sop_store") else "FAIL")
    r.add(phase="1", id="1.4", requirement="memory/knowledge_base.py", status="PASS" if _import("memory.knowledge_base") else "FAIL")
    r.add(phase="1", id="1.5", requirement="deploy/sql/init.sql 表结构", status="PASS" if _file_exists("deploy/sql/init.sql") else "FAIL")

    # Phase 2
    r.add(phase="2", id="2.1", requirement="agents/base.py", status="PASS" if _import("agents.base") else "FAIL")
    r.add(phase="2", id="2.2", requirement="agents/perception 爬虫+监控", status="PASS" if _import("agents.perception") else "FAIL")
    r.add(phase="2", id="2.3", requirement="PerceptionAgent execute", status="PASS" if _import("agents.perception.scraper") else "FAIL")

    # Phase 3
    r.add(phase="3", id="3.1", requirement="agents/strategy 选品+定价+出价", status="PASS" if _import("agents.strategy") else "FAIL")
    r.add(phase="3", id="3.2", requirement="ProductSelector", status="PASS" if _import("agents.strategy.product_selector") else "FAIL")
    r.add(phase="3", id="3.3", requirement="BiddingOptimizer", status="PASS" if _import("agents.strategy.bidding") else "FAIL")

    # Phase 4
    r.add(phase="4", id="4.1", requirement="agents/content 脚本+混剪+去重", status="PASS" if _import("agents.content") else "FAIL")
    r.add(phase="4", id="4.2", requirement="ScriptGenerator", status="PASS" if _import("agents.content.script_generator") else "FAIL")
    r.add(phase="4", id="4.3", requirement="VideoDeduplicator", status="PASS" if _import("agents.content.dedup") else "FAIL")

    # Phase 5
    r.add(phase="5", id="5.1", requirement="agents/execution 发布+调优", status="PASS" if _import("agents.execution") else "FAIL")
    r.add(phase="5", id="5.2", requirement="platform_apis douyin/kuaishou/weixin", status="PASS" if all(_import(f"agents.execution.platform_apis.{p}") for p in ("douyin", "kuaishou", "weixin")) else "FAIL")
    r.add(phase="5", id="5.3", requirement="AdOptimizer", status="PASS" if _import("agents.execution.ad_optimizer") else "FAIL")

    # Phase 6
    r.add(phase="6", id="6.1", requirement="orchestrator/state.py GlobalState", status="PASS" if _import("orchestrator.state") else "FAIL")
    r.add(phase="6", id="6.2", requirement="orchestrator/graph.py LangGraph", status="PASS" if _import("orchestrator.graph") else "FAIL")
    r.add(phase="6", id="6.3", requirement="orchestrator/nodes.py", status="PASS" if _import("orchestrator.nodes") else "FAIL")
    r.add(phase="6", id="6.4", requirement="orchestrator/roi_monitor.py", status="PASS" if _import("orchestrator.roi_monitor") else "FAIL")
    r.add(phase="6", id="6.5", requirement="main.py 入口", status="PASS" if _file_exists("main.py") else "FAIL")

    # Phase 7
    r.add(phase="7", id="7.1", requirement="api/routes.py Campaign API", status="PASS" if _import("api.routes") else "FAIL")
    r.add(phase="7", id="7.2", requirement="api/schemas.py", status="PASS" if _import("api.schemas") else "FAIL")
    r.add(phase="7", id="7.3", requirement="deploy/Dockerfile", status="PASS" if _file_exists("deploy/Dockerfile") else "FAIL")
    r.add(phase="7", id="7.4", requirement="pyproject.toml", status="PASS" if _file_exists("pyproject.toml") else "FAIL")
    r.add(phase="7", id="7.5", requirement="tests/integration/test_orchestrator.py", status="PASS" if _file_exists("tests/integration/test_orchestrator.py") else "FAIL")

    return r


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_checks()
    summary = report.summary()

    if args.json:
        print(json.dumps({"summary": summary, "checks": [asdict(c) for c in report.checks]}, ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("多智能体系统开发指南 — 验收报告")
        print("=" * 60)
        for c in report.checks:
            mark = {"PASS": "OK", "PARTIAL": "~", "FAIL": "X", "MISSING": "?"}[c.status]
            print(f"[{mark}] Phase {c.phase} {c.id}: {c.requirement}")
        print("-" * 60)
        print(f"PASS={summary['PASS']} PARTIAL={summary['PARTIAL']} FAIL={summary['FAIL']} MISSING={summary['MISSING']}")

    return 0 if summary["FAIL"] == 0 and summary["MISSING"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
