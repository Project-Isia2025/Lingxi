"""Phase 7 集成联调与部署验收。

用法:
  python scripts/acceptance_phase7.py
  python scripts/acceptance_phase7.py --live   # 启动 TestClient 跑 sync campaign
  python scripts/acceptance_phase7.py --json
"""
from __future__ import annotations

import argparse
import asyncio
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

Status = Literal["PASS", "FAIL", "SKIP"]


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
        out = {"PASS": 0, "FAIL": 0, "SKIP": 0}
        for c in self.checks:
            out[c.status] += 1
        return out


def static_checks(r: Report) -> None:
    files = [
        ("7.1", "api/routes.py", "Campaign FastAPI"),
        ("7.2", "api/schemas.py", "Pydantic 模型"),
        ("7.3", "deploy/Dockerfile", "部署镜像"),
        ("7.4", "tests/unit/", "单元测试目录"),
        ("7.5", "tests/integration/", "集成测试目录"),
        ("7.6", "tests/e2e/", "E2E 测试目录"),
    ]
    for cid, path, req in files:
        p = ROOT / path
        ok = p.is_file() or p.is_dir()
        r.add(id=cid, requirement=req, status="PASS" if ok else "FAIL", evidence=path)

    docker = (ROOT / "deploy/Dockerfile").read_text(encoding="utf-8")
    r.add(id="7.7", requirement="Dockerfile uvicorn api.routes:app", status="PASS" if "api.routes:app" in docker else "FAIL")
    r.add(id="7.8", requirement="Dockerfile FFmpeg", status="PASS" if "ffmpeg" in docker else "FAIL")

    try:
        from api.routes import app
        from api.schemas import CampaignRequest, CampaignResponse

        routes = {getattr(rt, "path", None) for rt in app.routes}
        r.add(id="7.9", requirement="/campaigns/start 路由", status="PASS" if "/campaigns/start" in routes else "FAIL")
        r.add(id="7.10", requirement="/health 路由", status="PASS" if "/health" in routes else "FAIL")
        assert CampaignRequest(goal="x")
        assert CampaignResponse(status="started", campaign_id="1")
    except Exception as exc:
        r.add(id="7.9", requirement="API 模块导入", status="FAIL", evidence=str(exc))


def live_checks(r: Report) -> None:
    try:
        from fastapi.testclient import TestClient
        from api.routes import app

        client = TestClient(app)
        h = client.get("/health")
        r.add(id="7.11", requirement="GET /health", status="PASS" if h.status_code == 200 else "FAIL", evidence=str(h.json()))

        resp = client.post(
            "/campaigns/start",
            json={"goal": "Phase7验收", "platform": "douyin", "budget": 50, "max_iterations": 1, "sync": True},
        )
        ok = resp.status_code == 200 and resp.json().get("campaign_id")
        r.add(id="7.12", requirement="POST /campaigns/start sync", status="PASS" if ok else "FAIL", evidence=resp.text[:200])

        if ok:
            cid = resp.json()["campaign_id"]
            st = client.get(f"/campaigns/{cid}/status")
            r.add(id="7.13", requirement="GET /campaigns/{id}/status", status="PASS" if st.status_code == 200 else "FAIL")
    except Exception as exc:
        r.add(id="7.11", requirement="Live API 探测", status="FAIL", evidence=str(exc))


async def main_async(live: bool, json_out: bool) -> int:
    r = Report()
    static_checks(r)
    if live:
        live_checks(r)
    else:
        r.add(id="live-skip", requirement="Live API（--live 启用）", status="SKIP")

    summary = r.summary()
    if json_out:
        print(json.dumps({"summary": summary, "checks": [asdict(c) for c in r.checks]}, ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("Phase 7 集成联调与部署验收")
        print("=" * 60)
        for c in r.checks:
            mark = {"PASS": "OK", "FAIL": "X", "SKIP": "-"}[c.status]
            print(f"[{mark}] {c.id}: {c.requirement}")
            if c.evidence:
                print(f"     {c.evidence}")
        print("-" * 60)
        print(f"PASS={summary['PASS']} FAIL={summary['FAIL']} SKIP={summary['SKIP']}")
    return 0 if summary["FAIL"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    return asyncio.run(main_async(args.live, args.json))


if __name__ == "__main__":
    raise SystemExit(main())
