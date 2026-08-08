"""审核拒因学习：打回原因写入知识库。"""
from __future__ import annotations

from core.storage import kb_upsert, save_episodic


def learn_from_rejection(
    *,
    run_id: str,
    review_id: str,
    reason: str,
    script: str = "",
    keyword: str = "",
    platform: str = "douyin",
) -> dict[str, object]:
    body = (reason or "").strip()
    if not body:
        return {"ok": False, "reason": "empty_reject_reason"}

    kb_id = kb_upsert(
        library="sop",
        title=f"审核打回·{review_id[:8]}",
        body=f"打回原因：{body}\n\n原脚本摘要：{(script or '')[:500]}",
        tags=f"review_reject,auto_learn,{keyword}",
        platform=platform,
    )
    save_episodic(
        run_id=run_id or review_id,
        agent="memory",
        observation=f"审核打回已学习：{body[:120]}",
        action="review_reject_learn",
        payload={"review_id": review_id, "kb_id": kb_id, "reject_reason": body},
    )
    return {"ok": True, "kb_id": kb_id}
