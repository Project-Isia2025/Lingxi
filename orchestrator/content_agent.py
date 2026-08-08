"""✍️ 内容 Agent（独立实现）。"""
from __future__ import annotations

from typing import Any

from orchestrator.base import AgentResult, BaseAgent
from orchestrator.context import WorkflowContext
from services.content import generate_content


def _build_source(ctx: WorkflowContext) -> str:
    strategy = ctx.strategy or {}
    perception = ctx.perception or {}
    memory = ctx.memory or {}
    keyword = (ctx.goal.keyword or ctx.goal.title or "").strip()
    angle = str(strategy.get("content_angle") or keyword)
    lines = [f"主题：{angle}", f"关键词：{keyword}"]
    top = (perception.get("competitors") or [None])[0]
    if isinstance(top, dict) and top.get("title"):
        lines.append(f"对标：{top['title']}")
    if isinstance(top, dict) and top.get("ocr_text"):
        lines.append(f"竞品OCR摘录：{str(top['ocr_text'])[:400]}")
    elif isinstance(top, dict) and top.get("body"):
        lines.append(f"竞品正文：{str(top['body'])[:400]}")
    for bd in (perception.get("breakdowns") or [])[:2]:
        if isinstance(bd, dict) and bd.get("original_transcript"):
            lines.append(f"参考笔记：{str(bd['original_transcript'])[:400]}")
    mat = str(memory.get("material_context") or "").strip()
    if mat:
        lines.append("素材库：\n" + mat[:1200])
    return "\n".join(lines)


class ContentAgent(BaseAgent):
    name = "content"
    phase = "content"

    def run(self, ctx: WorkflowContext) -> AgentResult:
        source = _build_source(ctx)
        if not source.strip():
            return AgentResult(ok=False, agent=self.name, phase=self.phase, message="无可用素材")

        keyword = (ctx.goal.keyword or ctx.goal.title or "").strip()
        angle = str((ctx.strategy or {}).get("content_angle") or keyword)
        extra = ctx.goal.extra or {}
        if extra.get("content_variant") == "B":
            variants = (ctx.strategy or {}).get("variants") or []
            for v in variants:
                if v.get("id") == "B" and v.get("angle"):
                    angle = str(v["angle"])
                    break
        content_out = generate_content(
            source=source,
            keyword=keyword,
            angle=angle,
            memory=ctx.memory or {},
            strategy=ctx.strategy or {},
            run_id=ctx.run_id,
            platform=(ctx.goal.platform or "douyin"),
            perception=ctx.perception or {},
        )
        ctx.content = content_out
        risk = content_out.get("risk_check") or {}
        dup = content_out.get("dedupe_duplicate")
        ctx.log(
            self.name,
            self.phase,
            "ok",
            f"脚本 {len(content_out.get('script',''))} 字，混剪 {len((content_out.get('mix_plan') or {}).get('timeline') or [])} 段",
        )

        conflicts: list[dict[str, Any]] = []
        if not risk.get("passed"):
            conflicts.append(
                {"type": "content_risk", "message": "含违禁词已替换，建议复核", "forbidden_count": risk.get("forbidden_count")}
            )
        if dup:
            conflicts.append(
                {
                    "type": "content_duplicate",
                    "message": (content_out.get("dedupe_info") or {}).get("recommendation"),
                    "similarity": (content_out.get("dedupe_info") or {}).get("similarity"),
                }
            )
        return AgentResult(
            ok=bool(content_out.get("script")),
            agent=self.name,
            phase=self.phase,
            data=content_out,
            message="内容生成完成",
            roi_delta=0.25,
            conflicts=conflicts,
        )
