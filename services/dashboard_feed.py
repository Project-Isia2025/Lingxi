"""Dashboard 感知 Feed 数据构建。"""
from __future__ import annotations

from typing import Any


def build_perception_feed(*, limit: int = 40) -> dict[str, Any]:
    from core.storage import kb_list_recent, list_episodic_recent, list_publish_queue_items

    items: list[dict[str, Any]] = []
    for row in kb_list_recent(tag_contains="asr", limit=limit):
        items.append({**row, "kind": "asr", "source": "kb"})
    for row in kb_list_recent(tag_contains="ocr", limit=limit):
        items.append({**row, "kind": "ocr", "source": "kb"})
    for row in kb_list_recent(tag_contains="publish_feedback", limit=20):
        items.append({**row, "kind": "publish", "source": "kb"})
    for row in kb_list_recent(tag_contains="combined_roi", limit=15):
        items.append({**row, "kind": "roi", "source": "kb"})
    items.sort(key=lambda x: int(x.get("updated_ts") or 0), reverse=True)

    episodes = list_episodic_recent(limit=limit)
    ep_items = []
    for ep in episodes:
        action = str(ep.get("action") or "")
        kind = ""
        if "asr" in action:
            kind = "asr"
        elif "ocr" in action:
            kind = "ocr"
        elif "publish" in action or "combined" in action:
            kind = "publish" if "publish" in action else "roi"
        if kind:
            ep_items.append(
                {
                    "kind": kind,
                    "title": ep.get("observation") or action,
                    "body": str((ep.get("payload") or {}).get("source_url") or (ep.get("payload") or {}).get("recommendation") or ""),
                    "platform": (ep.get("payload") or {}).get("platform") or "",
                    "updated_ts": ep.get("created_at"),
                    "source": "episodic",
                }
            )

    queue = list_publish_queue_items(limit=20)
    return {
        "ok": True,
        "items": items[:limit],
        "episodes": ep_items[:10],
        "publish_queue": queue,
    }
