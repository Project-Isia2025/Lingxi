"""Campaign API Pydantic 模型 — Phase 7 指南规范。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CampaignRequest(BaseModel):
    goal: str = Field(..., description="活动目标", min_length=1, max_length=500)
    platform: str = Field(default="douyin", description="目标平台")
    budget: float = Field(default=1000.0, ge=0, description="总预算")
    materials: list[str] = Field(default_factory=list, description="视频素材路径")
    max_iterations: int = Field(default=1, ge=1, le=10, description="最大迭代轮次")
    sync: bool = Field(default=False, description="同步等待完成（测试/调试）")


class CampaignResponse(BaseModel):
    status: str
    campaign_id: str


class CampaignStatusResponse(BaseModel):
    campaign_id: str
    status: str
    goal: str | None = None
    platform: str | None = None
    current_roi: float | None = None
    total_spend: float | None = None
    total_revenue: float | None = None
    iteration: int | None = None
    errors: list[str] | None = None
    stop_reason: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str = "content-commerce-agent"
    version: str = "1.0.0"
    checks: dict[str, Any] | None = None
