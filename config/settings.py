"""集中配置 — pydantic-settings，兼容现有 os.environ 读取。"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

import bootstrap

_TRUE = {"1", "true", "yes", "on"}


def _as_bool(v: object) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in _TRUE


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(bootstrap.project_root() / "config" / "local.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: str = "development"
    api_port: int = 9200
    debug: bool = False

    api_auth_enabled: bool = False
    api_auth_key: str = ""
    api_auth_admin_key: str = ""
    cors_origins: str = ""

    review_token_secret: str = ""
    rpa_webhook_secret: str = ""

    publish_queue_enabled: bool = False
    publish_queue_interval_sec: int = 300
    ad_poll_enabled: bool = False
    perception_schedule_enabled: bool = False
    roi_report_schedule_enabled: bool = False
    roi_alert_cleanup_enabled: bool = True
    post_publish_monitor_enabled: bool = True

    worker_backend: str = "celery"
    task_cleanup_enabled: bool = True
    docs_public_in_production: bool = False
    api_auth_allow_query_key: bool = False
    rpa_webhook_allow_open: bool = False
    worker_leader_lock_enabled: bool = True
    worker_leader_lock_ttl_sec: int = 120
    redis_host: str = "localhost"
    redis_port: int = 6379

    langgraph_orchestrator_enabled: bool = Field(
        default=False,
        description="LangGraph 编排为实验路径；生产默认使用 orchestrator_agent",
    )

    @field_validator(
        "debug",
        "api_auth_enabled",
        "publish_queue_enabled",
        "ad_poll_enabled",
        "perception_schedule_enabled",
        "roi_report_schedule_enabled",
        "roi_alert_cleanup_enabled",
        "post_publish_monitor_enabled",
        "worker_leader_lock_enabled",
        "task_cleanup_enabled",
        "docs_public_in_production",
        "api_auth_allow_query_key",
        "rpa_webhook_allow_open",
        "langgraph_orchestrator_enabled",
        mode="before",
    )
    @classmethod
    def _parse_bool_fields(cls, v: object) -> bool:
        return _as_bool(v)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")

    def cors_origin_list(self) -> list[str]:
        raw = (self.cors_origins or "").strip()
        if not raw:
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    def weak_review_secrets(self) -> frozenset[str]:
        return frozenset({"", "change-me-in-production", "matrix-review-dev"})

    def validate_production(self) -> list[str]:
        if not self.is_production:
            return []
        errors: list[str] = []
        if (self.review_token_secret or "").strip() in self.weak_review_secrets():
            errors.append("REVIEW_TOKEN_SECRET must be set to a strong random value in production")
        if not (self.rpa_webhook_secret or "").strip():
            errors.append("RPA_WEBHOOK_SECRET must be set in production")
        if not self.api_auth_enabled:
            errors.append("API_AUTH_ENABLED must be 1 in production")
        key = (self.api_auth_key or "").strip()
        if not key or len(key) < 16:
            errors.append("API_AUTH_KEY must be set (>=16 chars) in production")
        origins = self.cors_origin_list()
        if not (self.cors_origins or "").strip():
            errors.append("CORS_ORIGINS must be set in production (no default *)")
        elif "*" in origins:
            errors.append("CORS_ORIGINS must not contain * in production")
        return errors


@lru_cache
def get_settings() -> Settings:
    return Settings()


def sync_settings_to_environ() -> Settings:
    """将 Settings 同步到 os.environ（不覆盖已有变量，与 load_local_env 一致）。"""
    import os

    settings = get_settings()
    mapping = {
        "ENVIRONMENT": settings.environment,
        "API_PORT": str(settings.api_port),
        "DEBUG": "1" if settings.debug else "0",
        "API_AUTH_ENABLED": "1" if settings.api_auth_enabled else "0",
        "API_AUTH_KEY": settings.api_auth_key,
        "API_AUTH_ADMIN_KEY": settings.api_auth_admin_key,
        "CORS_ORIGINS": settings.cors_origins,
        "REVIEW_TOKEN_SECRET": settings.review_token_secret,
        "RPA_WEBHOOK_SECRET": settings.rpa_webhook_secret,
        "PUBLISH_QUEUE_ENABLED": "1" if settings.publish_queue_enabled else "0",
        "PUBLISH_QUEUE_INTERVAL_SEC": str(settings.publish_queue_interval_sec),
        "AD_POLL_ENABLED": "1" if settings.ad_poll_enabled else "0",
        "PERCEPTION_SCHEDULE_ENABLED": "1" if settings.perception_schedule_enabled else "0",
        "ROI_REPORT_SCHEDULE_ENABLED": "1" if settings.roi_report_schedule_enabled else "0",
        "ROI_ALERT_CLEANUP_ENABLED": "1" if settings.roi_alert_cleanup_enabled else "0",
        "POST_PUBLISH_MONITOR_ENABLED": "1" if settings.post_publish_monitor_enabled else "0",
        "WORKER_BACKEND": settings.worker_backend,
        "TASK_CLEANUP_ENABLED": "1" if settings.task_cleanup_enabled else "0",
        "DOCS_PUBLIC_IN_PRODUCTION": "1" if settings.docs_public_in_production else "0",
        "API_AUTH_ALLOW_QUERY_KEY": "1" if settings.api_auth_allow_query_key else "0",
        "RPA_WEBHOOK_ALLOW_OPEN": "1" if settings.rpa_webhook_allow_open else "0",
        "WORKER_LEADER_LOCK_ENABLED": "1" if settings.worker_leader_lock_enabled else "0",
        "WORKER_LEADER_LOCK_TTL_SEC": str(settings.worker_leader_lock_ttl_sec),
        "REDIS_HOST": settings.redis_host,
        "REDIS_PORT": str(settings.redis_port),
        "LANGGRAPH_ORCHESTRATOR_ENABLED": "1" if settings.langgraph_orchestrator_enabled else "0",
    }
    for key, val in mapping.items():
        if key not in os.environ and val:
            os.environ[key] = val
    return settings
