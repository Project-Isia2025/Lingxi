"""竞品数据爬虫 — Playwright + 现有 services 兜底。"""
from __future__ import annotations

from typing import Any


class CompetitorScraper:
    """竞品数据爬虫。"""

    def __init__(self) -> None:
        self.platforms = {
            "douyin": "https://www.douyin.com",
            "kuaishou": "https://www.kuaishou.com",
            "weixin": "https://channels.weixin.qq.com",
        }

    async def scrape_hot_products(self, platform: str, category: str | None = None) -> list[dict]:
        """抓取平台热销商品。"""
        if platform == "douyin":
            try:
                from services.douyin.hotlist import fetch_douyin_hotlist

                hot = fetch_douyin_hotlist(limit=10)
                items = hot.get("items") or hot.get("hotlist") or []
                if items:
                    return [
                        {
                            "name": i.get("title") or i.get("word") or f"热榜{i}",
                            "price": i.get("price"),
                            "sales": i.get("hot_value") or i.get("views"),
                            "url": i.get("url"),
                        }
                        for i in items
                        if isinstance(i, dict)
                    ]
            except Exception:
                pass

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return self._mock_products(platform, category)

        if platform not in self.platforms:
            return self._mock_products(platform, category)

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = await context.new_page()
                await page.goto(f"{self.platforms[platform]}/hot", timeout=15000)
                try:
                    await page.wait_for_selector('[data-testid="product-card"]', timeout=5000)
                    products = await page.evaluate(
                        """() => {
                        const cards = document.querySelectorAll('[data-testid="product-card"]');
                        return Array.from(cards).map(card => ({
                            name: card.querySelector('.product-name')?.textContent,
                            price: card.querySelector('.price')?.textContent,
                            sales: card.querySelector('.sales-count')?.textContent,
                            url: card.querySelector('a')?.href,
                        }));
                    }"""
                    )
                except Exception:
                    products = []
                await browser.close()
                if products:
                    return products
        except Exception:
            pass

        try:
            from services.perception import perceive_market

            out = perceive_market(keyword=category or "热销", platform=platform, include_hotlist=True)
            return [
                {
                    "name": c.get("title", ""),
                    "price": c.get("price"),
                    "sales": c.get("likes"),
                    "url": c.get("url"),
                }
                for c in (out.get("competitors") or [])
            ]
        except Exception:
            return self._mock_products(platform, category)

    async def scrape_competitor_videos(self, competitor_id: str) -> dict[str, Any]:
        """抓取竞品最新视频互动数据。"""
        url = competitor_id if str(competitor_id).startswith("http") else f"https://www.douyin.com/video/{competitor_id}"
        videos: list[dict] = []
        try:
            from services.douyin.video_detail import fetch_video_detail

            detail = fetch_video_detail(url)
            if detail.get("ok") or detail.get("title"):
                videos.append(
                    {
                        "video_id": detail.get("aweme_id") or competitor_id,
                        "title": detail.get("title") or detail.get("desc"),
                        "likes": detail.get("digg_count") or detail.get("likes"),
                        "comments": detail.get("comment_count"),
                        "shares": detail.get("share_count"),
                        "url": url,
                    }
                )
        except Exception:
            pass
        return {
            "competitor_id": competitor_id,
            "videos": videos,
            "status": "ok" if videos else "mock",
            "engagement": videos[0] if videos else {"likes": 0, "comments": 0},
        }

    @staticmethod
    def _mock_products(platform: str, category: str | None) -> list[dict]:
        return [
            {
                "name": f"{category or '热销'}商品{i}",
                "price": f"¥{29 + i * 10}.9",
                "sales": str(1000 + i * 500),
                "url": f"https://{platform}.example.com/p/{i}",
            }
            for i in range(1, 4)
        ]
