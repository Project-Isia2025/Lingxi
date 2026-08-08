#!/usr/bin/env python
"""3×15s 切片 + Avatar 成片 E2E 验收烟测（无需真实 API Key）。

用法:
  python scripts/acceptance_slice_e2e.py
  python scripts/acceptance_slice_e2e.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()


def _step(name: str, fn) -> dict[str, Any]:
    try:
        out = fn()
        ok = bool(out.get("ok", True)) if isinstance(out, dict) else bool(out)
        return {"step": name, "ok": ok, "result": out}
    except Exception as exc:
        return {"step": name, "ok": False, "error": str(exc)[:300]}


def run_e2e(*, keyword: str = "A面膜") -> dict[str, Any]:
    steps: list[dict[str, Any]] = []

    def check_slice_drafts() -> dict[str, Any]:
        from services.slice_drafts import generate_slice_drafts

        strategy = {
            "variants": [
                {"id": "S1", "hook_style": "痛点反问", "brief": "切片1"},
                {"id": "S2", "hook_style": "结果先行", "brief": "切片2"},
                {"id": "S3", "hook_style": "对比冲击", "brief": "切片3"},
            ],
            "daily_directive": {"primary_product": {"name": "A款面膜"}},
        }
        pack = generate_slice_drafts(
            base_script="测试口播。痛点描述。解决方案。",
            keyword=keyword,
            strategy=strategy,
            product_name="A款面膜",
        )
        if pack.get("count") != 3:
            return {"ok": False, "error": "expected_3_drafts", "pack": pack}
        return {"ok": True, "count": 3, "draft_ids": [d["id"] for d in pack["drafts"]]}

    steps.append(_step("slice_drafts_generate", check_slice_drafts))

    def check_avatar_mock() -> dict[str, Any]:
        from unittest.mock import patch

        from services.video_providers.avatar import produce

        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src.mp4"
            src.write_bytes(b"fake-video")
            with patch("services.video_providers.http_client.api_credentials", return_value=("", "")):
                out = produce(
                    script="数字人口播测试",
                    run_id=f"e2e-{uuid.uuid4().hex[:6]}",
                    source_video=str(src),
                )
        return out

    steps.append(_step("avatar_mock_produce", check_avatar_mock))

    def check_slice_render() -> dict[str, Any]:
        from unittest.mock import patch

        from services.slice_drafts import generate_slice_drafts, render_slice_drafts

        strategy = {
            "variants": [
                {"id": "S1", "hook_style": "痛点反问"},
                {"id": "S2", "hook_style": "结果先行"},
                {"id": "S3", "hook_style": "对比冲击"},
            ],
        }
        pack = generate_slice_drafts(
            base_script="测试脚本。",
            keyword=keyword,
            strategy=strategy,
        )
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src.mp4"
            src.write_bytes(b"fake")
            with patch("services.slice_drafts.render_mix_video") as mock_render:
                mock_render.side_effect = lambda **kw: {
                    "ok": True,
                    "output_path": str(Path(td) / f"{kw.get('output_name', 'out')}.mp4"),
                }
                out = render_slice_drafts(
                    drafts=pack["drafts"],
                    source_video=str(src),
                    run_id="e2e-slice",
                    keyword=keyword,
                    provider="avatar",
                )
        return out

    steps.append(_step("slice_render_batch", check_slice_render))

    def check_review_batch() -> dict[str, Any]:
        from unittest.mock import patch

        from services.review_queue import submit_batch_for_review

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "e2e.db"
            paths = []
            for i in range(3):
                p = Path(td) / f"v{i}.mp4"
                p.write_bytes(b"x")
                paths.append(str(p))
            with patch("core.storage.DB_PATH", db), patch(
                "services.feishu_review.send_review_card",
                return_value={"ok": True},
            ):
                from core.storage import init_storage

                init_storage()
                return submit_batch_for_review(
                    run_id="e2e-review",
                    items=[
                        {"video_path": paths[i], "script": f"脚本{i}", "title": f"切片{i+1}"}
                        for i in range(3)
                    ],
                    notify_feishu=False,
                )

    steps.append(_step("review_batch_submit", check_review_batch))

    def check_providers_api() -> dict[str, Any]:
        from services.video_providers.router import list_providers, video_gen_enabled

        providers = list_providers()
        return {"ok": "avatar" in providers, "providers": providers, "enabled": video_gen_enabled()}

    steps.append(_step("video_providers_registry", check_providers_api))

    passed = sum(1 for s in steps if s.get("ok"))
    return {
        "ok": passed == len(steps),
        "passed": passed,
        "total": len(steps),
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="3×15s + Avatar E2E 验收烟测")
    parser.add_argument("--keyword", default="A面膜")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_e2e(keyword=args.keyword)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"E2E 烟测: {report['passed']}/{report['total']} 通过")
        for step in report["steps"]:
            mark = "OK" if step.get("ok") else "FAIL"
            print(f"  [{mark}] {step['step']}")
            if not step.get("ok"):
                print(f"       {step.get('error') or step.get('result')}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
