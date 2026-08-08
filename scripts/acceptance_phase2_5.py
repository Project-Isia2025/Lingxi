"""Phase 2-5 四个子 Agent 验收脚本。

用法:
  python scripts/acceptance_phase2_5.py
  python scripts/acceptance_phase2_5.py --json
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
    phase: str
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


def _import(path: str) -> bool:
    try:
        importlib.import_module(path)
        return True
    except Exception:
        return False


def _file(path: str) -> bool:
    return (ROOT / path).is_file()


def static_checks(r: Report) -> None:
    structure = [
        ("2", "agents/base.py", "agents/base.py"),
        ("2", "agents/perception/scraper.py", "agents/perception/scraper.py"),
        ("2", "agents/perception/monitor.py", "agents/perception/monitor.py"),
        ("2", "agents/perception/cleaners.py", "agents/perception/cleaners.py"),
        ("3", "agents/strategy/product_selector.py", "agents/strategy/product_selector.py"),
        ("3", "agents/strategy/pricing.py", "agents/strategy/pricing.py"),
        ("3", "agents/strategy/bidding.py", "agents/strategy/bidding.py"),
        ("4", "agents/content/script_generator.py", "agents/content/script_generator.py"),
        ("4", "agents/content/video_editor.py", "agents/content/video_editor.py"),
        ("4", "agents/content/dedup.py", "agents/content/dedup.py"),
        ("5", "agents/execution/publisher.py", "agents/execution/publisher.py"),
        ("5", "agents/execution/ad_optimizer.py", "agents/execution/ad_optimizer.py"),
        ("5", "agents/execution/platform_apis/douyin.py", "agents/execution/platform_apis/douyin.py"),
        ("5", "agents/execution/platform_apis/kuaishou.py", "agents/execution/platform_apis/kuaishou.py"),
        ("5", "agents/execution/platform_apis/weixin.py", "agents/execution/platform_apis/weixin.py"),
    ]
    for phase, req, path in structure:
        r.add(phase=phase, id=path, requirement=req, status="PASS" if _file(path) else "FAIL")

    for phase, name, mod in (
        ("2", "PerceptionAgent", "agents.perception"),
        ("3", "StrategyAgent", "agents.strategy"),
        ("4", "ContentAgent", "agents.content"),
        ("5", "ExecutionAgent", "agents.execution"),
    ):
        r.add(phase=phase, id=f"import-{name}", requirement=f"{name} 可导入", status="PASS" if _import(mod) else "FAIL")


async def functional_checks(r: Report) -> None:
    from agents.content import ContentAgent
    from agents.execution import ExecutionAgent
    from agents.perception import PerceptionAgent
    from agents.strategy import StrategyAgent

    p = PerceptionAgent()
    p_out = await p.run({"type": "scrape_products", "platform": "douyin", "category": "护肤"})
    r.add(phase="2", id="2.1", requirement="感知-爬虫+清洗+入库", status="PASS" if p_out.get("count", 0) >= 1 else "FAIL", evidence=f"count={p_out.get('count')}")

    t_out = await p.run({"type": "check_traffic"})
    r.add(phase="2", id="2.2", requirement="感知-流量监控", status="PASS" if "traffic_report" in t_out else "FAIL")

    s = StrategyAgent()
    s_out = await s.run(
        {
            "type": "full_strategy",
            "criteria": {"keyword": "护肤", "realtime_products": p_out.get("products", []), "platform": "douyin"},
            "budget": 300,
            "history": [{"bid": 0.8, "conversions": 10}, {"bid": 1.2, "conversions": 18}],
        }
    )
    r.add(phase="3", id="3.1", requirement="策略-选品+定价+出价", status="PASS" if s_out.get("product") else "FAIL")

    c = ContentAgent()
    c_out = await c.run(
        {
            "type": "generate_script",
            "product": s_out.get("product") or {"name": "护肤面膜", "selling_points": ["补水"]},
            "style": "激情带货",
        }
    )
    r.add(phase="4", id="4.1", requirement="内容-脚本生成+违禁词", status="PASS" if c_out.get("script", {}).get("raw_script") else "FAIL")

    v_out = await c.run(
        {
            "type": "produce_video",
            "product": s_out.get("product") or {"name": "护肤面膜"},
            "materials": [],
            "output_path": "data/output/videos/phase25_test.mp4",
        }
    )
    r.add(phase="4", id="4.2", requirement="内容-混剪+去重", status="PASS" if v_out.get("video_path") else "FAIL")

    e = ExecutionAgent()
    e_out = await e.run(
        {
            "type": "publish",
            "video_path": v_out.get("video_path", "data/output/videos/mock.mp4"),
            "metadata": {"title": "Phase25测试", "tags": ["测试"]},
            "platforms": ["douyin", "kuaishou", "weixin"],
        }
    )
    pub = e_out.get("publish_result", {})
    ok_count = sum(1 for p in ("douyin", "kuaishou", "weixin") if pub.get(p, {}).get("status") == "success")
    r.add(phase="5", id="5.1", requirement="执行-三平台发布", status="PASS" if ok_count == 3 else "FAIL", evidence=f"success={ok_count}/3")

    opt = await e.run({"type": "optimize_ads"})
    r.add(phase="5", id="5.2", requirement="执行-投流调优", status="PASS" if "optimization_report" in opt else "FAIL")

    from agents.pipeline import run_pipeline

    pipe = await run_pipeline({"keyword": "测试", "platform": "douyin", "budget": 100})
    r.add(phase="5", id="5.3", requirement="四 Agent 串联 pipeline", status="PASS" if pipe.get("ok") else "FAIL")


async def main_async(json_out: bool) -> int:
    r = Report()
    static_checks(r)
    await functional_checks(r)
    summary = r.summary()
    if json_out:
        print(json.dumps({"summary": summary, "checks": [asdict(c) for c in r.checks]}, ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("Phase 2-5 四个子 Agent 验收")
        print("=" * 60)
        for c in r.checks:
            mark = "OK" if c.status == "PASS" else "X"
            print(f"[{mark}] Phase {c.phase} {c.id}: {c.requirement}")
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
