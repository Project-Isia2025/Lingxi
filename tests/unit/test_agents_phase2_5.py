"""Phase 2-5 四个子 Agent 单元测试。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


def test_agent_registry():
    from agents import AGENT_REGISTRY, get_agent, list_agents

    names = list_agents()
    assert set(names) == {"perception", "strategy", "content", "execution"}
    for n in names:
        agent = get_agent(n)
        assert agent.name == n


@pytest.mark.asyncio
async def test_perception_modules():
    from agents.perception.cleaners import clean_products, parse_price
    from agents.perception.monitor import TrafficMonitor
    from agents.perception.scraper import CompetitorScraper

    assert parse_price("¥29.9") == 29.9
    cleaned = clean_products([{"name": "A", "price": "10"}, {"name": "A", "price": "11"}], "douyin")
    assert len(cleaned) == 1

    scraper = CompetitorScraper()
    products = await scraper.scrape_hot_products("douyin", "护肤")
    assert products

    monitor = TrafficMonitor()
    report = await monitor.check_all()
    assert "campaigns" in report


@pytest.mark.asyncio
async def test_strategy_modules():
    from agents.strategy.bidding import BiddingOptimizer
    from agents.strategy.pricing import PricingModel
    from agents.strategy.product_selector import ProductSelector

    selector = ProductSelector()
    selected = await selector.select({"keyword": "面膜", "realtime_products": [{"name": "面膜A", "price": 29}]})
    assert selected

    pricing = PricingModel().calculate({"cost_price": 10}, [{"price": 30}, {"price": 40}])
    assert pricing["strategy"] == "competitive"

    bidding = BiddingOptimizer().optimize(100, [{"bid": 1, "conversions": 5}, {"bid": 2, "conversions": 12}])
    assert bidding["strategy"] == "optimized"


@pytest.mark.asyncio
async def test_content_modules():
    from agents.content.dedup import VideoDeduplicator
    from agents.content.script_generator import ScriptGenerator

    gen = ScriptGenerator()
    script = await gen.generate({"name": "测试商品", "selling_points": ["A", "B"]})
    assert "Hook" in script["raw_script"] or "【" in script["raw_script"]

    dedup = VideoDeduplicator()
    result = dedup.is_duplicate("data/output/videos/phase25_test.mp4", [])
    assert result["is_duplicate"] is False


@pytest.mark.asyncio
async def test_execution_platforms():
    from agents.execution.platform_apis.douyin import DouyinAPI
    from agents.execution.platform_apis.kuaishou import KuaishouAPI
    from agents.execution.platform_apis.weixin import WeixinAPI
    from agents.execution.publisher import Publisher

    pub = Publisher()
    out = await pub.publish(
        "data/output/videos/mock.mp4",
        {"title": "t", "tags": []},
        ["douyin", "kuaishou", "weixin"],
    )
    assert all(out[p]["status"] == "success" for p in ("douyin", "kuaishou", "weixin"))

    assert DouyinAPI()._mock_mode
    assert KuaishouAPI()._mock_mode
    assert WeixinAPI()._mock_mode


@pytest.mark.asyncio
async def test_four_agent_pipeline():
    from agents import get_agent

    p = await get_agent("perception").run({"type": "scrape_products", "platform": "douyin"})
    s = await get_agent("strategy").run(
        {
            "type": "full_strategy",
            "criteria": {"keyword": "护肤", "realtime_products": p["products"]},
            "budget": 200,
        }
    )
    c = await get_agent("content").run(
        {
            "type": "generate_script",
            "product": s.get("product") or {"name": "护肤"},
        }
    )
    e = await get_agent("execution").run(
        {
            "type": "optimize_ads",
        }
    )
    assert p["count"] >= 1
    assert "script" in c
    assert "optimization_report" in e
