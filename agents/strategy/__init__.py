"""策略 Agent — 选品 / 定价 / 投放出价。"""
from __future__ import annotations

from agents.base import BaseAgent
from agents.strategy.bidding import BiddingOptimizer
from agents.strategy.pricing import PricingModel
from agents.strategy.product_selector import ProductSelector
from memory.knowledge_base import KnowledgeBase


class StrategyAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("strategy")
        self.selector = ProductSelector()
        self.pricing = PricingModel()
        self.bidding = BiddingOptimizer()
        self.kb = KnowledgeBase()

    async def execute(self, task: dict) -> dict:
        task_type = task.get("type")

        if task_type == "select_product":
            products = await self.selector.select(criteria=task["criteria"], top_n=task.get("top_n", 10))
            await self.kb.log_decision(
                agent_name=self.name,
                decision_type="select_product",
                input_data=task.get("criteria"),
                output_data={"count": len(products)},
                confidence=products[0]["score"] if products else 0,
            )
            return {"selected_products": products}

        if task_type == "pricing":
            result = self.pricing.calculate(product=task["product"], competitors=task.get("competitors", []))
            return {"pricing": result}

        if task_type == "bidding":
            result = self.bidding.optimize(budget=task["budget"], historical_data=task.get("history", []))
            return {"bidding": result}

        if task_type == "full_strategy":
            products = await self.selector.select(task["criteria"])
            if not products:
                return {"error": "no suitable product found"}
            product = products[0]
            pricing = self.pricing.calculate(product, task.get("competitors", []))
            bidding = self.bidding.optimize(task["budget"], task.get("history", []))
            result = {"product": product, "pricing": pricing, "bidding": bidding}
            await self.kb.log_decision(
                agent_name=self.name,
                decision_type="full_strategy",
                input_data={"criteria": task.get("criteria"), "budget": task.get("budget")},
                output_data=result,
                confidence=float(product.get("score") or 0),
            )
            return result

        raise ValueError(f"Unknown task type: {task_type}")


__all__ = ["StrategyAgent", "ProductSelector", "PricingModel", "BiddingOptimizer"]
