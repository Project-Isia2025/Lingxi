"""Phase 6 LangGraph 总控大脑验收。

用法:
  python scripts/acceptance_phase6.py
  python scripts/acceptance_phase6.py --json
"""
from __future__ import annotations

import argparse
import asyncio
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

Status = Literal["PASS", "FAIL"]


@dataclass
class Check:
    id: str
    requirement: str
    status: Status
    evidence: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, **kwargs) -> None:
        self.checks.append(Check(**kwargs))

    def summary(self) -> dict[str, int]:
        out = {"PASS": 0, "FAIL": 0}
        for c in self.checks:
            out[c.status] += 1
        return out


def static_checks(r: Report) -> None:
    files = [
        ("6.1", "orchestrator/state.py", "GlobalState"),
        ("6.2", "orchestrator/graph.py", "LangGraph Orchestrator"),
        ("6.3", "orchestrator/nodes.py", "编排节点"),
        ("6.4", "orchestrator/roi_monitor.py", "ROI 监控"),
        ("6.5", "main.py", "LangGraph CLI 入口"),
        ("6.6", "orchestrator/orchestrator_agent.py", "原有工作流保留"),
    ]
    for cid, path, req in files:
        r.add(id=cid, requirement=req, status="PASS" if (ROOT / path).is_file() else "FAIL", evidence=path)

    try:
        from orchestrator import Orchestrator, OrchestratorAgent, build_initial_state, run_workflow
        from orchestrator.graph import Orchestrator as GraphOrch

        r.add(id="6.7", requirement="LangGraph 与 OrchestratorAgent 并存", status="PASS", evidence="both importable")
        assert Orchestrator is GraphOrch
        assert callable(run_workflow)
        assert callable(build_initial_state)
    except Exception as exc:
        r.add(id="6.7", requirement="LangGraph 与 OrchestratorAgent 并存", status="FAIL", evidence=str(exc))


async def functional_checks(r: Report) -> None:
    from orchestrator.graph import Orchestrator
    from orchestrator.roi_monitor import ROIMonitor
    from orchestrator.state import build_initial_state

    info = Orchestrator().graph_info()
    r.add(id="6.8", requirement="状态图节点完整", status="PASS" if len(info["nodes"]) >= 6 else "FAIL", evidence=str(info["nodes"]))

    state = build_initial_state(goal="Phase6测试", platform="douyin", total_budget=200, max_iterations=1)
    r.add(id="6.9", requirement="build_initial_state", status="PASS" if state.get("run_id") else "FAIL")

    monitor = ROIMonitor()
    r.add(id="6.10", requirement="ROI 监控 should_stop", status="PASS" if monitor.should_stop({**state, "iteration": 1, "current_roi": 0.5})[0] else "FAIL")

    orch = Orchestrator()
    final = await orch.run(initial_state={**state, "max_iterations": 1})
    ok = (
        final.get("iteration", 0) > 0
        and "perception_data" in final
        and "strategy_data" in final
        and "content_data" in final
        and "execution_data" in final
    )
    r.add(
        id="6.11",
        requirement="LangGraph 全链路 ainvoke",
        status="PASS" if ok else "FAIL",
        evidence=f"iteration={final.get('iteration')} roi={final.get('current_roi')}",
    )


async def main_async(json_out: bool) -> int:
    r = Report()
    static_checks(r)
    await functional_checks(r)
    summary = r.summary()
    if json_out:
        print(json.dumps({"summary": summary, "checks": [asdict(c) for c in r.checks]}, ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("Phase 6 LangGraph 总控大脑验收")
        print("=" * 60)
        for c in r.checks:
            mark = "OK" if c.status == "PASS" else "X"
            print(f"[{mark}] {c.id}: {c.requirement}")
            if c.evidence:
                print(f"     {c.evidence}")
        print("-" * 60)
        print(f"PASS={summary['PASS']} FAIL={summary['FAIL']}")
    return 0 if summary["FAIL"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    return asyncio.run(main_async(parser.parse_args().json))


if __name__ == "__main__":
    raise SystemExit(main())
