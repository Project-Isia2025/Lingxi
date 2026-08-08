"""数据感知：竞品库、热点、流量趋势、参考链接结构分析。"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
import os

import bootstrap
from core.storage import metrics_summary, seed_kb_if_empty


def _score_item(item: dict[str, Any]) -> float:
    likes = float(item.get("likes") or item.get("digg_count") or 0)
    comments = float(item.get("comments") or item.get("comment_count") or 0)
    return likes + comments * 3


def _curated_competitors(keyword: str, platform: str, *, limit: int = 15) -> list[dict[str, Any]]:
    seed_kb_if_empty()
    path = bootstrap.project_root() / "data" / "competitors.json"
    items: list[dict[str, Any]] = []
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                items = [x for x in raw if isinstance(x, dict)]
        except Exception:
            items = []
    if not items:
        key = (keyword or "护肤").strip()
        items = [
            {"title": f"{key}避坑指南｜90%的人做错了", "platform": "douyin", "likes": 8200, "comments": 430, "views": 120000, "url": "https://example.com/v/1"},
            {"title": f"实测{key}一个月，真实变化记录", "platform": "douyin", "likes": 5600, "comments": 210, "views": 95000, "url": "https://example.com/v/2"},
            {"title": f"{key}怎么选？内行人才知道的3个标准", "platform": "xiaohongshu", "likes": 3100, "comments": 180, "views": 80000, "url": "https://example.com/v/3"},
        ]
    key = (keyword or "").strip().lower()
    plat = (platform or "").strip().lower()
    filtered = []
    for item in items:
        blob = f"{item.get('title','')} {item.get('desc','')}".lower()
        p = str(item.get("platform") or "").lower()
        if plat and p and p not in (plat, "all"):
            continue
        if key and key not in blob and not any(t in blob for t in key.split() if len(t) >= 2):
            continue
        filtered.append(item)
    pool = filtered or items
    return sorted(pool, key=_score_item, reverse=True)[:limit]


def _fetch_rss_hotspots(keyword: str, *, limit: int = 8) -> list[dict[str, Any]]:
    sources_path = bootstrap.project_root() / "data" / "hotspot_sources.json"
    sources: list[str] = []
    if sources_path.is_file():
        try:
            data = json.loads(sources_path.read_text(encoding="utf-8"))
            sources = [str(x) for x in (data.get("rss") or data if isinstance(data, list) else []) if str(x).startswith("http")]
        except Exception:
            pass
    if not sources:
        return [
            {"title": f"{keyword}季节热度上升", "source": "curated", "body": "搜索量周环比+18%"},
            {"title": "成分党内容互动率更高", "source": "curated", "body": "对比测评类完播率更高"},
        ]
    key = (keyword or "").lower()
    hits: list[dict[str, Any]] = []
    strip = re.compile(r"<[^>]+>")
    for url in sources[:3]:
        try:
            req = Request(url, headers={"User-Agent": "MatrixAgent/1.0"})
            with urlopen(req, timeout=10) as resp:
                root = ET.fromstring(resp.read())
            for item in root.findall(".//item")[:20]:
                title = unescape(strip.sub("", item.findtext("title") or "")).strip()
                desc = unescape(strip.sub("", item.findtext("description") or "")).strip()
                if key and key not in title.lower() and key not in desc.lower():
                    continue
                hits.append({"title": title[:120], "body": desc[:300], "source": url})
        except Exception:
            continue
    return hits[:limit]


def analyze_reference_url(url: str, *, keyword: str = "") -> dict[str, Any]:
    """无外部视频依赖的结构拆解（黄金五段式模板）。"""
    title = keyword or "爆款内容"
    segments = [
        {"name": "钩子", "start": 0, "end": 3, "hint": f"用反问切入：为什么{title}总是踩坑？"},
        {"name": "痛点", "start": 3, "end": 12, "hint": "描述目标用户真实场景与后果"},
        {"name": "方案", "start": 12, "end": 25, "hint": "给出可执行的三步方法"},
        {"name": "证据", "start": 25, "end": 40, "hint": "案例/数据/前后对比增强信任"},
        {"name": "行动", "start": 40, "end": 55, "hint": "明确 CTA：评论/私信/下单"},
    ]
    return {
        "url": url,
        "ok": True,
        "breakdown_segments": segments,
        "original_transcript": f"【参考链接】{url} — 建议按黄金五段式重写「{title}」主题口播。",
    }


def traffic_trend(metrics: dict[str, Any]) -> dict[str, Any]:
    by_event = metrics.get("by_event") or {}
    publish = int((by_event.get("publish_ok") or {}).get("count") or 0)
    leads = int(metrics.get("leads_total") or 0)
    trend = "stable"
    if leads >= 3 or publish >= 2:
        trend = "rising"
    elif publish == 0 and leads == 0:
        trend = "cold_start"
    return {
        "trend": trend,
        "publish_count": publish,
        "leads_total": leads,
    }


def traffic_volatility(competitors: list[dict[str, Any]], hotspots: list[dict[str, Any]]) -> dict[str, Any]:
    """基于竞品互动分布与热点密度估算流量波动。"""
    scores = [_score_item(c) for c in competitors[:10]]
    if not scores:
        return {"level": "unknown", "score_spread": 0, "hotspot_count": len(hotspots)}
    avg = sum(scores) / len(scores)
    mx = max(scores)
    spread = (mx - avg) / max(avg, 1.0)
    hotspot_n = len(hotspots)
    level = "stable"
    if spread >= 1.2 and hotspot_n >= 2:
        level = "high_opportunity"
    elif spread >= 0.6:
        level = "moderate"
    return {
        "level": level,
        "score_spread": round(spread, 2),
        "hotspot_count": hotspot_n,
        "top_score": round(mx, 1),
        "avg_score": round(avg, 1),
        "signal": "头部爆款与腰部差距大，适合差异化切入" if level == "high_opportunity" else "竞争均衡，需强化钩子",
    }


def rank_viral_candidates(competitors: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    ranked = sorted(competitors, key=_score_item, reverse=True)[:limit]
    out = []
    for i, c in enumerate(ranked):
        score = _score_item(c)
        tier = "S" if score >= 8000 else "A" if score >= 4000 else "B"
        out.append(
            {
                "rank": i + 1,
                "title": str(c.get("title") or "")[:100],
                "url": c.get("url") or "",
                "likes": c.get("likes"),
                "viral_score": round(score, 1),
                "tier": tier,
            }
        )
    return out


def _fetch_douyin_competitors(
    keyword: str,
    *,
    min_likes: int = 0,
    min_followers: int = 0,
    min_like_rate: float | None = None,
    limit: int = 15,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """优先真实爬虫，失败则回退样本库。"""
    from services.perception_engagement import filter_by_like_rate

    meta: dict[str, Any] = {"source": "curated", "crawler": None}
    plat = "douyin"
    if plat and keyword:
        try:
            from services.douyin.search import search_douyin

            result = search_douyin(
                keyword,
                min_likes=min_likes,
                min_followers=min_followers,
                min_like_rate=None,
                limit=limit,
            )
            meta["crawler"] = result
            if result.get("ok") and result.get("items"):
                meta["source"] = "live_crawler"
                items = list(result["items"])
                if os.environ.get("DOUYIN_ENRICH_DETAIL", "1").strip().lower() not in ("0", "false", "no", "off"):
                    try:
                        from services.douyin.video_detail import enrich_competitors

                        enrich_limit = int(os.environ.get("DOUYIN_ENRICH_LIMIT", "5") or 5)
                        items = enrich_competitors(items, limit=enrich_limit)
                        meta["detail_enriched"] = True
                        meta["detail_enrich_count"] = sum(1 for c in items if c.get("detail_fetched"))
                    except Exception as exc:
                        meta["detail_enrich_error"] = str(exc)
                passed, skipped = filter_by_like_rate(items, min_rate=min_like_rate, strict=True)
                meta["like_rate_filtered"] = {"passed": len(passed), "skipped": len(skipped)}
                return passed or items[:limit], meta
            meta["crawler_error"] = result.get("error") or result.get("hint")
        except Exception as exc:
            meta["crawler_error"] = str(exc)
    items = _curated_competitors(keyword, plat, limit=limit)
    for c in items:
        c["views_from_detail"] = True
    passed, skipped = filter_by_like_rate(items, min_rate=min_like_rate, strict=False)
    meta["like_rate_filtered"] = {"passed": len(passed), "skipped": len(skipped)}
    return passed or items, meta


def _fetch_xhs_competitors(
    keyword: str,
    *,
    min_likes: int = 0,
    limit: int = 15,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"source": "curated", "crawler": None}
    if keyword:
        try:
            from services.xhs.search import search_xhs

            result = search_xhs(keyword, min_likes=min_likes, limit=limit)
            meta["crawler"] = result
            if result.get("ok") and result.get("items"):
                meta["source"] = "live_crawler"
                return list(result["items"]), meta
            meta["crawler_error"] = result.get("error") or result.get("hint")
        except Exception as exc:
            meta["crawler_error"] = str(exc)
    return _curated_competitors(keyword, "xiaohongshu", limit=limit), meta


def _enrich_xhs_reference_breakdowns(
    breakdowns: list[dict[str, Any]],
    reference_urls: list[str],
    *,
    keyword: str,
) -> list[dict[str, Any]]:
    out = list(breakdowns)
    for url in reference_urls[:3]:
        if "xiaohongshu.com" not in url:
            continue
        try:
            from services.xhs.note_detail import fetch_note_detail

            detail = fetch_note_detail(url)
            if not detail.get("ok"):
                continue
            body = str(detail.get("body") or "")
            asr_text = str(detail.get("asr_text") or "")
            ocr_text = str(detail.get("ocr_text") or "")
            segments = [
                {"name": "钩子", "start": 0, "end": 3, "hint": (detail.get("title") or "")[:40]},
                {"name": "正文", "start": 3, "end": 30, "hint": body[:120]},
                {"name": "标签", "start": 30, "end": 40, "hint": "、".join(detail.get("tags") or [])[:80]},
            ]
            if asr_text:
                segments.insert(1, {"name": "ASR口播", "start": 3, "end": 20, "hint": asr_text[:120]})
            out.append(
                {
                    "url": url,
                    "ok": True,
                    "platform": "xiaohongshu",
                    "breakdown_segments": segments,
                    "original_transcript": (asr_text or body)[:2000],
                    "asr_text": asr_text,
                    "ocr_text": ocr_text,
                    "tags": detail.get("tags") or [],
                    "likes": detail.get("likes"),
                }
            )
            if asr_text:
                try:
                    from services.asr_memory import ingest_asr_transcript

                    ingest_asr_transcript(
                        text=asr_text,
                        title=str(detail.get("title") or ""),
                        platform="xiaohongshu",
                        note_id=str(detail.get("note_id") or ""),
                        source_url=url,
                        keyword=keyword,
                    )
                except Exception:
                    pass
        except Exception:
            continue
    return out[:5]


def perceive_market(
    *,
    keyword: str,
    platform: str,
    reference_urls: list[str],
    min_likes: int = 0,
    min_followers: int = 0,
    min_like_rate: float | None = None,
    limit: int = 15,
    include_hotlist: bool = False,
) -> dict[str, Any]:
    hotlist_items: list[dict[str, Any]] = []
    if include_hotlist or os.environ.get("PERCEPTION_INCLUDE_HOTLIST", "1").strip().lower() in ("1", "true", "yes", "on"):
        try:
            from services.douyin.hotlist import fetch_douyin_hotlist

            hot = fetch_douyin_hotlist(limit=10)
            hotlist_items = list(hot.get("items") or [])
        except Exception:
            hotlist_items = []

    competitors: list[dict[str, Any]]
    crawl_meta: dict[str, Any]
    try:
        from services.rpa_ingest import fetch_rpa_competitors

        rpa_items, rpa_meta = fetch_rpa_competitors(keyword, platform, limit=limit)
        if rpa_items:
            competitors = rpa_items
            crawl_meta = rpa_meta
        else:
            competitors = []
            crawl_meta = {}
    except Exception:
        competitors = []
        crawl_meta = {}

    if not competitors:
        if (platform or "douyin").strip().lower() in ("douyin", "tiktok"):
            competitors, crawl_meta = _fetch_douyin_competitors(
                keyword,
                min_likes=min_likes,
                min_followers=min_followers,
                min_like_rate=min_like_rate,
                limit=limit,
            )
        elif (platform or "").strip().lower() in ("xiaohongshu", "xhs"):
            competitors, crawl_meta = _fetch_xhs_competitors(
                keyword,
                min_likes=min_likes,
                limit=limit,
            )
            if os.environ.get("XHS_ENRICH_DETAIL", "1").strip().lower() not in ("0", "false", "no"):
                try:
                    from services.xhs.note_detail import enrich_competitors

                    enrich_limit = int(os.environ.get("XHS_ENRICH_LIMIT", "3") or 3)
                    competitors = enrich_competitors(competitors, limit=enrich_limit)
                    crawl_meta["enriched"] = True
                    crawl_meta["enrich_count"] = sum(1 for c in competitors if c.get("detail_fetched"))
                except Exception as exc:
                    crawl_meta["enrich_error"] = str(exc)
        else:
            competitors = _curated_competitors(keyword, platform, limit=limit)
            crawl_meta = {"source": "curated"}
            if min_likes > 0:
                competitors = [c for c in competitors if int(c.get("likes") or 0) >= min_likes]
    hotspots = _fetch_rss_hotspots(keyword)
    metrics = metrics_summary(days=14)
    trend = traffic_trend(metrics)
    breakdowns = [analyze_reference_url(u, keyword=keyword) for u in reference_urls[:3] if u.startswith("http")]
    breakdowns = _enrich_xhs_reference_breakdowns(breakdowns, reference_urls, keyword=keyword)
    signals = [
        {
            "title": str(c.get("title") or "")[:120],
            "url": c.get("url") or "",
            "score": round(_score_item(c), 1),
            "likes": c.get("likes"),
        }
        for c in competitors[:5]
    ]
    volatility = traffic_volatility(competitors, hotspots)
    viral_rank = rank_viral_candidates(competitors)
    insights = {}
    if os.environ.get("PERCEPTION_INSIGHTS_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off"):
        try:
            from services.perception_insights import ingest_competitor_insights

            insights = ingest_competitor_insights(competitors=competitors, keyword=keyword)
        except Exception as exc:
            insights = {"ok": False, "error": str(exc)}

    return {
        "keyword": keyword,
        "platform": platform,
        "competitors": competitors,
        "crawl_meta": crawl_meta,
        "traffic_signals": signals,
        "hotspots": hotspots,
        "hotlist": hotlist_items,
        "breakdowns": breakdowns,
        "historical_metrics": metrics,
        "traffic_trend": trend,
        "traffic_volatility": volatility,
        "viral_rank": viral_rank,
        "insights_ingested": insights,
    }


def run_perception_scan(
    *,
    keyword: str,
    platform: str = "douyin",
    run_id: str = "",
    include_hotlist: bool = True,
) -> dict[str, Any]:
    """定时/手动感知扫描：热榜 + 竞品 + 点赞率过滤 + 洞察入库。"""
    min_rate = None
    try:
        raw = os.environ.get("PERCEPTION_MIN_LIKE_RATE", "0.05")
        if raw.strip():
            min_rate = float(raw)
    except ValueError:
        min_rate = 0.05

    out = perceive_market(
        keyword=keyword,
        platform=platform,
        reference_urls=[],
        min_like_rate=min_rate,
        limit=int(os.environ.get("PERCEPTION_COMPETITOR_LIMIT", "15") or 15),
        include_hotlist=include_hotlist,
    )
    out["run_id"] = run_id
    out["ok"] = True
    return out
