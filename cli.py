#!/usr/bin/env python
"""命令行启动六 Agent 工作流。"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()


def _parse_platforms(raw: str) -> list[str]:
    return [p.strip().lower() for p in (raw or "").split(",") if p.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="五层 AI 智能体矩阵 — 工作流 CLI")
    parser.add_argument("--keyword", required=True, help="选品/竞品关键词")
    parser.add_argument("--title", default="", help="Campaign 名称")
    parser.add_argument("--platform", default="douyin", help="douyin | xiaohongshu | xhs | shipinhao")
    parser.add_argument("--budget", type=float, default=0, help="成片预算上限 CNY")
    parser.add_argument("--url", action="append", default=[], dest="urls", help="参考视频 URL，可多次")
    parser.add_argument("--video-path", default="", dest="video_path", help="本地 B-roll/成片路径")
    parser.add_argument("--source-video", default="", dest="source_video", help="B-roll 源视频（混剪/切片用）")
    parser.add_argument("--product-image", default="", dest="product_image", help="商品图/数字人参考图")
    parser.add_argument(
        "--video-provider",
        default="",
        dest="video_provider",
        help="AI 成片 provider: avatar | volc | kling | template",
    )
    parser.add_argument("--org-id", default="", dest="org_id", help="租户 org_id（多账号隔离）")
    parser.add_argument("--slice-drafts", action="store_true", dest="slice_drafts", help="启用 3×15s 独立切片初稿")
    parser.add_argument("--auto-execute", action="store_true", help="自动创建视频任务")
    parser.add_argument("--auto-publish", action="store_true", help="自动发布到创作者中心")
    parser.add_argument("--auto-matrix", action="store_true", dest="auto_matrix_publish", help="联合 ROI 矩阵入队")
    parser.add_argument(
        "--publish-platforms",
        default="",
        help="发布平台列表，逗号分隔，如 douyin,xiaohongshu",
    )
    parser.add_argument("--enable-replan", action="store_true", help="启用 Plan→Observe→Replan")
    parser.add_argument("--max-iterations", type=int, default=2, help="Replan 最大轮次")
    parser.add_argument("--sync", action="store_true", help="同步执行（默认异步）")
    parser.add_argument("--poll", action="store_true", help="异步模式下轮询直到完成")
    args = parser.parse_args()

    if args.slice_drafts:
        os.environ["SLICE_DRAFTS_ENABLED"] = "1"

    from orchestrator.context import WorkflowGoal
    from orchestrator.orchestrator_agent import run_workflow
    from orchestrator.workflow_store import load_run

    extra: dict = {}
    plats = _parse_platforms(args.publish_platforms)
    if plats:
        extra["publish_platforms"] = plats

    broll = (args.source_video or args.video_path or "").strip()
    if broll:
        extra["source_video"] = broll
    if args.product_image.strip():
        extra["product_image"] = args.product_image.strip()
    if args.slice_drafts:
        extra["slice_drafts"] = True
    if args.org_id.strip():
        extra["org_id"] = args.org_id.strip()

    goal = WorkflowGoal(
        title=args.title,
        keyword=args.keyword.strip(),
        platform=args.platform,
        budget_limit=args.budget,
        auto_execute=args.auto_execute,
        auto_publish=bool(args.auto_publish),
        auto_matrix_publish=bool(args.auto_matrix_publish),
        video_path=broll,
        video_provider=(args.video_provider or "").strip(),
        org_id=args.org_id.strip(),
        reference_urls=args.urls,
        enable_replan=bool(args.enable_replan),
        max_iterations=max(1, min(int(args.max_iterations or 2), 5)),
        extra=extra,
    )
    ctx = run_workflow(goal, async_mode=not args.sync)
    run_id = ctx.run_id
    print(json.dumps({"run_id": run_id, "status": ctx.status}, ensure_ascii=False))

    if args.poll and not args.sync:
        for _ in range(120):
            time.sleep(2)
            data = load_run(run_id) or {}
            status = str(data.get("status") or "")
            stage = str(data.get("stage") or "")
            print(f"[poll] stage={stage} status={status}", file=sys.stderr)
            if status in ("completed", "failed", "cancelled"):
                print(json.dumps(data, ensure_ascii=False, indent=2))
                return 0 if status == "completed" else 1
        print("poll timeout", file=sys.stderr)
        return 2

    if args.sync:
        out = ctx.to_dict()
        execution = out.get("execution") or {}
        slice_render = execution.get("slice_render") or {}
        if slice_render.get("count"):
            print(
                json.dumps(
                    {
                        "slice_drafts_rendered": slice_render.get("count"),
                        "recommended": slice_render.get("recommended"),
                        "review_ids": (execution.get("review") or {}).get("review_ids"),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if ctx.status == "completed" else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
