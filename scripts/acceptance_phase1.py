"""Phase 1 记忆与知识库验收脚本。

对照开发指南 Phase 1:
  - vector_store.py 向量库读写
  - banned_words.py 违禁词检测
  - sop_store.py SOP 双写检索
  - knowledge_base.py 统一入口
  - memory/data/banned_words.json
  - deploy/sql/init.sql 表结构

用法:
  python scripts/acceptance_phase1.py
  python scripts/acceptance_phase1.py --json
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


async def _functional_checks(r: Report) -> None:
    from memory import BannedWordsFilter, KnowledgeBase, VectorStore

    vs = VectorStore()
    pid = await vs.add("scripts", "夏季防晒霜爆款口播模板", {"title": "防晒脚本", "platform": "douyin"})
    hits = await vs.search("scripts", "防晒霜", limit=3)
    r.add(
        id="1.1",
        requirement="VectorStore add/search",
        status="PASS" if hits and pid else "FAIL",
        evidence=f"point={pid}, hits={len(hits)}",
    )

    bw = BannedWordsFilter()
    hits_bw = bw.check("这是国家级最好产品，100%有效")
    sanitized = bw.sanitize("最好产品")
    r.add(
        id="1.2",
        requirement="BannedWordsFilter check/sanitize",
        status="PASS" if hits_bw and "****" in sanitized else "FAIL",
        evidence=f"hits={hits_bw}",
    )

    kb = KnowledgeBase()
    sop = await kb.add_sop("带货", "3秒钩子", "你知道吗？夏天不防晒老十岁！", ["hook", "防晒"])
    sop_hits = await kb.search_sop("防晒钩子")
    r.add(
        id="1.3",
        requirement="SOPDocument add/search",
        status="PASS" if sop and sop_hits else "FAIL",
        evidence=f"sop={sop.get('title')}, hits={len(sop_hits)}",
    )

    product = await kb.ingest_hot_product(
        {"platform": "douyin", "name": "测试面膜", "price": 29.9, "sales": 1200, "trend_score": 0.8}
    )
    ctx = await kb.retrieve_context(query="面膜护肤", platform="douyin")
    r.add(
        id="1.4",
        requirement="KnowledgeBase hot_product + retrieve_context",
        status="PASS" if product and ctx.get("query") else "FAIL",
        evidence=f"product={product.get('product_name') or product.get('name')}",
    )

    decision = await kb.log_decision(
        agent_name="strategy",
        decision_type="select_product",
        input_data={"keyword": "面膜"},
        output_data=product if isinstance(product, dict) else {"id": getattr(product, "id", None)},
        confidence=0.85,
    )
    r.add(
        id="1.5",
        requirement="AgentDecision 日志",
        status="PASS" if decision else "FAIL",
        evidence=str(decision),
    )


def _static_checks(r: Report) -> None:
    files = [
        ("1.0", "memory/vector_store.py", "memory/vector_store.py"),
        ("1.0b", "memory/banned_words.py", "memory/banned_words.py"),
        ("1.0c", "memory/sop_store.py", "memory/sop_store.py"),
        ("1.0d", "memory/knowledge_base.py", "memory/knowledge_base.py"),
        ("1.0e", "memory/data/banned_words.json", "memory/data/banned_words.json"),
        ("1.0f", "memory/models.py", "memory/models.py"),
        ("1.0g", "memory/repository.py", "memory/repository.py"),
        ("1.0h", "deploy/sql/init.sql", "deploy/sql/init.sql"),
    ]
    for cid, req, path in files:
        r.add(id=cid, requirement=req, status="PASS" if (ROOT / path).is_file() else "FAIL")

    sql = (ROOT / "deploy/sql/init.sql").read_text(encoding="utf-8")
    for table in ("hot_products", "ad_campaigns", "agent_decisions", "sop_documents"):
        r.add(
            id=f"sql-{table}",
            requirement=f"SQL 表 {table}",
            status="PASS" if table in sql else "FAIL",
        )


async def main_async(json_out: bool) -> int:
    r = Report()
    _static_checks(r)
    await _functional_checks(r)
    summary = r.summary()
    if json_out:
        print(json.dumps({"summary": summary, "checks": [asdict(c) for c in r.checks]}, ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("Phase 1 记忆与知识库验收")
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
    args = parser.parse_args()
    return asyncio.run(main_async(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
