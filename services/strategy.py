"""策略：内容角度、选品定价、成本路由、投流出价。"""
from __future__ import annotations

import os
from typing import Any

from services.ad_optimizer import build_ad_plan


PAID = {"volc": 1.5, "kling": 2.0, "longcat": 1.2, "avatar": 2.5, "heygen": 3.0, "capcut": 1.8, "jianying": 1.8}
LOW_COST = {"template", "manual", "storyboard"}


def plan_video_cost(*, provider: str, script: str, budget_limit: float = 0) -> dict[str, Any]:
    pid = (provider or "template").strip().lower()
    chars = len(script or "")
    est = PAID.get(pid, 0.0)
    if pid in LOW_COST:
        est = 0.0
    budget = float(budget_limit or 0) or float(os.environ.get("VIDEO_BUDGET_LIMIT", "0") or 0)
    selected = pid
    reason = "within_budget"
    approval = False
    if budget > 0 and est > budget:
        approval = True
        selected = os.environ.get("VIDEO_FALLBACK_PROVIDER", "template")
        reason = "over_budget_downgrade"
    return {
        "requested_provider": pid,
        "selected_provider": selected,
        "estimated_cost": round(est, 2),
        "budget_limit": budget,
        "approval_required": approval and selected == pid,
        "route_reason": reason,
        "estimated_seconds": max(3.0, chars / 4.0),
    }


def infer_content_angle(keyword: str, perception: dict, memory: dict) -> str:
    viral = (memory.get("viral_structure") or [])
    if viral:
        names = [s.get("name") for s in viral[0].get("segments") or [] if s.get("name")]
        if names:
            return f"黄金结构（{'→'.join(names[:3])}），关键词：{keyword}"
    top = (perception.get("competitors") or [None])[0]
    if isinstance(top, dict) and top.get("title"):
        return f"对标「{top['title'][:60]}」，主题：{keyword}"
    return f"痛点+解决方案型口播，关键词：{keyword}"


def select_product(keyword: str, perception: dict, memory: dict) -> dict[str, Any]:
    """基于竞品互动与知识库推断选品/主推角度。"""
    competitors = perception.get("competitors") or []
    viral = perception.get("viral_rank") or []
    top = viral[0] if viral else (competitors[0] if competitors else {})
    likes = int(top.get("likes") or 0) if isinstance(top, dict) else 0
    kb_hot = (memory.get("top_kb_items") or [])
    product_type = "引流款"
    if likes >= 5000:
        product_type = "爆款对标款"
    elif kb_hot:
        product_type = "利润款"
    return {
        "primary_product": keyword or "主推SKU",
        "product_type": product_type,
        "reference_title": str(top.get("title") or "")[:80],
        "selection_reason": f"竞品互动 {likes}，类型 {product_type}",
        "bundle_hint": "引流款+利润款组合，短视频推引流、私信推利润",
    }


def pricing_tiers(keyword: str, perception: dict) -> list[dict[str, Any]]:
    competitors = perception.get("competitors") or []
    avg_likes = 0
    if competitors:
        avg_likes = sum(int(c.get("likes") or 0) for c in competitors[:5]) // max(1, min(5, len(competitors)))
    base = 99 if avg_likes < 3000 else 199 if avg_likes < 8000 else 299
    return [
        {"tier": "引流", "price_cny": max(9.9, round(base * 0.1, 1)), "role": "私信/直播间转化"},
        {"tier": "主力", "price_cny": base, "role": f"{keyword}核心方案"},
        {"tier": "高客单", "price_cny": round(base * 2.5, 0), "role": "1v1/年度服务"},
    ]


def ad_bid_hint(trend: dict) -> str:
    if trend.get("trend") == "rising":
        return "历史表现良好，建议逐步放量，优先高完播素材"
    if trend.get("trend") == "cold_start":
        return "冷启动：小预算测 3 条素材，CTR>2% 再扩量"
    return "维持稳定投放，每周替换 1-2 条低效素材"


def render_channel_preview(script: str, geo: dict) -> dict[str, str]:
    brand = geo.get("brand_name") or "品牌"
    cta = geo.get("cta_text") or "私信领取资料"
    hook = (script or "")[:36].strip() or "这件事很多人忽略了"
    return {
        "short_video_script": f"{script.strip()}\n\n{cta}",
        "moments_post": f"{hook}\n\n{script[:240]}\n\n{cta}",
        "dm_script": f"你好，看到你对{hook[:12]}感兴趣，{cta}",
        "community_post": f"【分享】{hook}\n{script[:400]}\n{cta}",
        "poster_copy": f"主标题：{hook[:16]}\n副标题：{brand}\n行动：{cta}",
    }


def build_strategy(
    *,
    keyword: str,
    platform: str,
    perception: dict,
    memory: dict,
    budget_limit: float,
    video_provider: str,
) -> dict[str, Any]:
    from services.daily_directive import build_daily_directive
    from services.inventory import get_primary_product

    inv = get_primary_product()
    inventory_product = inv.get("product") if inv.get("ok") else None
    if inventory_product and not keyword:
        keyword = str(inventory_product.get("keyword") or inventory_product.get("name") or keyword)

    daily = build_daily_directive(keyword=keyword, perception=perception, memory=memory, product=inventory_product)
    angle = infer_content_angle(keyword, perception, memory)
    draft = f"【{keyword}】{angle}"[:300]
    provider = video_provider or os.environ.get("VIDEO_PROVIDER", "template")
    cost = plan_video_cost(provider=provider, script=draft, budget_limit=budget_limit)
    geo = memory.get("geo") or {}
    trend = perception.get("traffic_trend") or {}
    product = select_product(keyword, perception, memory)
    pricing = pricing_tiers(keyword, perception)
    ad_plan = build_ad_plan(
        keyword=keyword,
        platform=platform,
        strategy={"content_angle": angle},
        perception=perception,
        budget_limit=budget_limit,
    )
    from agents.strategy.bidding import BiddingOptimizer

    bid_budget = float(budget_limit or 0) or float(ad_plan.get("daily_budget_cny") or 100)
    bidding = BiddingOptimizer().optimize(bid_budget, [])
    conflicts = []
    if cost.get("approval_required"):
        conflicts.append(
            {
                "type": "budget_over_limit",
                "selected": cost.get("selected_provider") or os.environ.get("VIDEO_FALLBACK_PROVIDER", "template"),
                "fallback_provider": os.environ.get("VIDEO_FALLBACK_PROVIDER", "template"),
                "estimated_cost": cost.get("estimated_cost"),
                "budget_limit": cost.get("budget_limit"),
            }
        )
    daily_budget = float(ad_plan.get("daily_budget_cny") or 0)
    if budget_limit > 0 and daily_budget > budget_limit:
        conflicts.append(
            {
                "type": "ad_budget_high",
                "daily_budget_cny": daily_budget,
                "budget_limit": budget_limit,
            }
        )
    bid_cpc = float(bidding.get("bid_cpc") or 0)
    if bid_cpc > 2.0:
        conflicts.append(
            {
                "type": "high_bid",
                "bid_cpc": bid_cpc,
                "daily_budget_cny": daily_budget,
                "budget_limit": budget_limit,
            }
        )
    channels = ["short_video", "moments_post", "dm_script"]
    if platform in ("xiaohongshu", "xhs"):
        channels.append("community_post")
    variants = [
        {"id": s["id"], "angle": s["brief"], "hook_style": s["hook_style"], "duration_sec": s["duration_sec"]}
        for s in (daily.get("slices") or [])
    ]
    if not variants:
        variants = [
            {"id": "A", "angle": angle, "hook_style": "痛点反问"},
            {"id": "B", "angle": f"案例型：{product.get('reference_title', keyword) if isinstance(product, dict) else keyword}", "hook_style": "结果先行"},
        ]
    return {
        "content_angle": angle,
        "target_platform": platform,
        "primary_keyword": keyword,
        "reference_competitor": (perception.get("competitors") or [None])[0],
        "product_selection": product,
        "inventory_product": inventory_product,
        "daily_directive": daily,
        "pricing_tiers": pricing,
        "channels": channels,
        "variants": variants,
        "channel_preview": render_channel_preview(draft, geo),
        "cta": geo.get("cta_text") or "私信领取资料",
        "pricing_hint": product.get("bundle_hint") or "引流款 + 利润款组合",
        "ad_bid_hint": ad_bid_hint(trend),
        "ad_plan": ad_plan,
        "bidding": bidding,
        "video_cost_plan": cost,
        "selected_provider": cost.get("selected_provider"),
        "traffic_trend": trend,
        "traffic_volatility": perception.get("traffic_volatility") or {},
        "_conflicts": conflicts,
    }