"""LangGraph 总控大脑 CLI 入口。

用法:
  python main.py
  python main.py --goal "推广防晒霜" --platform douyin --budget 5000
  python main.py --max-iterations 1
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()

from orchestrator.graph import Orchestrator
from orchestrator.state import build_initial_state


async def main(args: argparse.Namespace) -> int:
    orchestrator = Orchestrator()
    initial = build_initial_state(
        goal=args.goal,
        platform=args.platform,
        total_budget=args.budget,
        max_iterations=args.max_iterations,
        materials=args.materials,
    )

    print(f"[LangGraph] 启动 run_id={initial['run_id']}")
    print(f"[LangGraph] 节点: {' -> '.join(orchestrator.NODE_SEQUENCE)}")

    final_state = await orchestrator.graph.ainvoke(initial)

    summary = {
        "run_id": final_state.get("run_id"),
        "status": final_state.get("status"),
        "current_roi": final_state.get("current_roi"),
        "total_spend": final_state.get("total_spend"),
        "total_revenue": final_state.get("total_revenue"),
        "iteration": final_state.get("iteration"),
        "errors": final_state.get("errors"),
        "stop_reason": final_state.get("stop_reason"),
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("-" * 40)
        print(f"最终 ROI: {final_state.get('current_roi', 0):.2f}")
        print(f"总消耗:   {final_state.get('total_spend', 0):.2f}")
        print(f"总收入:   {final_state.get('total_revenue', 0):.2f}")
        print(f"迭代次数: {final_state.get('iteration', 0)}")
        print(f"状态:     {final_state.get('status')}")
        if final_state.get("errors"):
            print(f"错误:     {final_state['errors']}")

    return 0 if not final_state.get("errors") else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LangGraph 总控大脑")
    parser.add_argument("--goal", default="推广一款夏季防晒霜，目标 ROAS > 2.0")
    parser.add_argument("--platform", default="douyin")
    parser.add_argument("--budget", type=float, default=5000.0)
    parser.add_argument("--max-iterations", type=int, default=10)
    parser.add_argument("--materials", nargs="*", default=[])
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(parse_args())))
