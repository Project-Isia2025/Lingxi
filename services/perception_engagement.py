"""竞品互动率（点赞率）计算与过滤。"""
from __future__ import annotations

import os
from typing import Any


def default_min_like_rate() -> float:
    try:
        return max(0.0, min(float(os.environ.get("PERCEPTION_MIN_LIKE_RATE", "0.05")), 1.0))
    except ValueError:
        return 0.05


def compute_like_rate(*, likes: int | float | None, views: int | float | None) -> float | None:
    if likes is None or views is None:
        return None
    try:
        lv = float(likes)
        vv = float(views)
    except (TypeError, ValueError):
        return None
    if vv <= 0:
        return None
    return round(lv / vv, 4)


def enrich_item_engagement(item: dict[str, Any]) -> dict[str, Any]:
    """为竞品条目补充 views / like_rate 字段。"""
    out = dict(item)
    likes = out.get("likes")
    views = out.get("views") or out.get("play_count")
    if views is None and likes is not None:
        try:
            lv = int(likes)
            if lv > 0:
                views = max(lv * 12, lv + 100)
                out["views_estimated"] = True
        except (TypeError, ValueError):
            pass
    rate = compute_like_rate(likes=likes, views=views)
    out["views"] = views
    out["like_rate"] = rate
    return out


def filter_by_like_rate(
    items: list[dict[str, Any]],
    *,
    min_rate: float | None = None,
    strict: bool | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """返回 (通过列表, 被过滤列表)。

    strict=True 时：无真实 views 或 like_rate 不达标的条目一律过滤。
    """
    threshold = default_min_like_rate() if min_rate is None else float(min_rate)
    if strict is None:
        strict = os.environ.get("PERCEPTION_REQUIRE_REAL_VIEWS", "1").strip().lower() in (
            "1", "true", "yes", "on",
        )

    if threshold <= 0 and not strict:
        return [enrich_item_engagement(x) for x in items], []

    passed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for raw in items:
        item = enrich_item_engagement(raw)
        rate = item.get("like_rate")
        estimated = bool(item.get("views_estimated"))
        has_real_views = bool(item.get("views_from_detail")) or (
            item.get("views") is not None and not estimated
        )

        if strict and not has_real_views:
            skipped.append({**item, "skip_reason": "no_real_views"})
            continue
        if rate is None:
            if strict:
                skipped.append({**item, "skip_reason": "no_like_rate"})
            else:
                passed.append(item)
            continue
        if rate >= threshold:
            passed.append(item)
        else:
            skipped.append({**item, "skip_reason": "like_rate_below_threshold"})
    return passed, skipped
