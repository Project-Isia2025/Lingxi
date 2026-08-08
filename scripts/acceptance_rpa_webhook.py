#!/usr/bin/env python
"""影刀 RPA Webhook + 字段映射 + 感知回写验收。

用法:
  python scripts/acceptance_rpa_webhook.py
  python scripts/acceptance_rpa_webhook.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()
bootstrap.load_local_env()


def run_rpa_webhook_acceptance() -> dict:
    from fastapi.testclient import TestClient

    from api_server import app
    from services.rpa_ingest import build_rpa_integration_guide, fetch_rpa_competitors, ingest_rpa_webhook

    steps: list[dict] = []
    example_path = ROOT / "data" / "yingdao_webhook.example.json"
    payload = json.loads(example_path.read_text(encoding="utf-8")) if example_path.is_file() else {
        "platform": "douyin",
        "keyword": "护肤",
        "items": [{"title": "验收爆款", "url": "https://example.com/v", "likes": 1000}],
    }

    with tempfile.TemporaryDirectory() as td:
        store = Path(td) / "rpa.json"
        mapping = ROOT / "data" / "rpa_field_mapping.example.json"
        with patch.dict(
            "os.environ",
            {
                "RPA_INGEST_PATH": str(store),
                "RPA_WEBHOOK_SECRET": "",
                "RPA_FIELD_MAPPING_PATH": str(mapping),
            },
        ):
            # 中文字段映射（影刀常见列名）
            yingdao_payload = {
                "platform": "douyin",
                "keyword": "护肤",
                "items": [
                    {
                        "标题": "影刀映射测试1",
                        "链接": "https://example.com/yd1",
                        "点赞数": 5000,
                    }
                ],
            }
            ing = ingest_rpa_webhook(yingdao_payload, source="yingdao")
            steps.append({"step": "ingest_yingdao_mapped", "ok": bool(ing.get("ok")), "result": ing})

            items, meta = fetch_rpa_competitors("护肤", "douyin", limit=5)
            steps.append(
                {
                    "step": "fetch_perception",
                    "ok": len(items) >= 1 and meta.get("source") == "rpa_webhook",
                    "result": {"count": len(items), "meta": meta},
                }
            )

            guide = build_rpa_integration_guide(base_url="http://127.0.0.1:9200")
            steps.append(
                {
                    "step": "integration_guide",
                    "ok": bool(guide.get("ok")) and "yingdao" in (guide.get("webhook_urls") or {}),
                    "result": {"urls": guide.get("webhook_urls")},
                }
            )

    client = TestClient(app)
    r = client.get("/api/rpa/guide")
    steps.append({"step": "guide_api", "ok": r.status_code == 200 and r.json().get("ok"), "result": {}})

    with patch.dict("os.environ", {"RPA_WEBHOOK_SECRET": ""}, clear=False):
        r2 = client.post("/api/rpa/webhook/yingdao", json=payload)
    steps.append({"step": "webhook_api", "ok": r2.status_code == 200 and r2.json().get("ok"), "result": r2.json()})

    passed = sum(1 for s in steps if s.get("ok"))
    return {
        "ok": passed == len(steps),
        "passed": passed,
        "total": len(steps),
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run_rpa_webhook_acceptance()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for s in report.get("steps") or []:
            mark = "OK" if s.get("ok") else "FAIL"
            print(f"[{mark}] {s.get('step')}")
        print(f"\n{report.get('passed')}/{report.get('total')} passed")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
