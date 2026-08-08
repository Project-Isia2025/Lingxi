"""API 鉴权分级策略 — 按路由匹配 public / webhook / review / read / write / admin。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class AuthTier(str, Enum):
    """鉴权等级（数值越大要求越高）。"""

    PUBLIC = "public"
    WEBHOOK = "webhook"
    REVIEW = "review"
    DASHBOARD = "dashboard"
    STATIC = "static"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


# 中间件需校验 API Key 的等级
_PROTECTED_TIERS = frozenset({AuthTier.READ, AuthTier.WRITE, AuthTier.ADMIN})


@dataclass(frozen=True)
class AuthRule:
    methods: frozenset[str]
    pattern: re.Pattern[str]
    tier: AuthTier
    note: str = ""


def _m(*methods: str) -> frozenset[str]:
    return frozenset(m.upper() for m in methods)


# 规则按顺序匹配，先声明的优先
_AUTH_RULES: tuple[AuthRule, ...] = (
    # --- 完全公开 ---
    AuthRule(_m("*"), re.compile(r"^/$"), AuthTier.PUBLIC, "root"),
    AuthRule(_m("OPTIONS"), re.compile(r".*"), AuthTier.PUBLIC, "cors-preflight"),
    AuthRule(_m("GET"), re.compile(r"^/api/health$"), AuthTier.PUBLIC, "liveness"),
    AuthRule(_m("GET"), re.compile(r"^/api/health/ready$"), AuthTier.PUBLIC, "readiness"),
    AuthRule(_m("GET"), re.compile(r"^/metrics$"), AuthTier.PUBLIC, "prometheus"),
    AuthRule(_m("GET"), re.compile(r"^/api/auth/status$"), AuthTier.PUBLIC, "auth-status"),
    AuthRule(_m("GET"), re.compile(r"^/api/auth/policy$"), AuthTier.PUBLIC, "auth-policy"),
    AuthRule(_m("POST"), re.compile(r"^/api/auth/login$"), AuthTier.PUBLIC, "auth-login"),
    AuthRule(_m("GET"), re.compile(r"^/openapi\.json$"), AuthTier.PUBLIC, "openapi"),
    # --- 静态 / 文档 ---
    AuthRule(_m("GET"), re.compile(r"^/docs(?:/|$)"), AuthTier.STATIC, "swagger"),
    AuthRule(_m("GET"), re.compile(r"^/redoc(?:/|$)"), AuthTier.STATIC, "redoc"),
    AuthRule(_m("GET"), re.compile(r"^/static/"), AuthTier.STATIC, "static"),
    # --- Webhook（端点内校验 RPA / 飞书 secret）---
    AuthRule(_m("POST"), re.compile(r"^/api/rpa/webhook"), AuthTier.WEBHOOK, "rpa-webhook"),
    AuthRule(_m("POST"), re.compile(r"^/api/review/callback$"), AuthTier.WEBHOOK, "feishu-review"),
    # --- 审核外链（端点内校验 review token）---
    AuthRule(
        _m("GET", "POST"),
        re.compile(r"^/api/review/[^/]+/(approve|reject-form)(/|$)"),
        AuthTier.REVIEW,
        "review-action",
    ),
    AuthRule(
        _m("POST"),
        re.compile(r"^/api/review/[^/]+/reject$"),
        AuthTier.REVIEW,
        "review-reject",
    ),
    # --- Dashboard HTML（页面公开；子 API 走 READ/WRITE）---
    AuthRule(_m("GET"), re.compile(r"^/dashboard(?:/|$)"), AuthTier.DASHBOARD, "dashboard-ui"),
    # --- 高危 / 管理 ---
    AuthRule(_m("POST"), re.compile(r"^/api/orchestrator/run$"), AuthTier.ADMIN, "orchestrator-run"),
    AuthRule(_m("POST"), re.compile(r"^/api/orchestrator/langgraph/run$"), AuthTier.ADMIN, "langgraph-run"),
    AuthRule(_m("POST"), re.compile(r"^/api/orchestrator/runs/[^/]+/cancel$"), AuthTier.ADMIN, "run-cancel"),
    AuthRule(_m("POST"), re.compile(r"^/api/publish/run$"), AuthTier.ADMIN, "publish-run"),
    AuthRule(_m("POST"), re.compile(r"^/api/publish/run_multi$"), AuthTier.ADMIN, "publish-run-multi"),
    AuthRule(_m("POST"), re.compile(r"^/api/publish/matrix(?:/auto)?$"), AuthTier.ADMIN, "publish-matrix"),
    AuthRule(_m("POST"), re.compile(r"^/api/publish/schedule$"), AuthTier.ADMIN, "publish-schedule"),
    AuthRule(_m("POST"), re.compile(r"^/api/publish/queue/[^/]+/cancel$"), AuthTier.ADMIN, "queue-cancel"),
    AuthRule(_m("POST"), re.compile(r"^/api/ad/deploy$"), AuthTier.ADMIN, "ad-deploy"),
    AuthRule(_m("POST"), re.compile(r"^/api/workflow/start$"), AuthTier.ADMIN, "workflow-start"),
    AuthRule(_m("POST"), re.compile(r"^/api/workflow/runs/[^/]+/cancel$"), AuthTier.ADMIN, "workflow-cancel"),
    AuthRule(_m("POST"), re.compile(r"^/api/video/produce$"), AuthTier.ADMIN, "video-produce"),
    AuthRule(_m("POST"), re.compile(r"^/api/agents/pipeline/run$"), AuthTier.ADMIN, "agents-pipeline"),
    AuthRule(_m("POST"), re.compile(r"^/api/agents/[^/]+/run$"), AuthTier.ADMIN, "agent-run"),
    AuthRule(_m("POST"), re.compile(r"^/campaigns/start$"), AuthTier.ADMIN, "campaign-start"),
    AuthRule(_m("POST"), re.compile(r"^/api/orgs/[^/]+/webhooks$"), AuthTier.ADMIN, "org-webhooks"),
    AuthRule(_m("POST"), re.compile(r"^/api/review/submit$"), AuthTier.ADMIN, "review-submit"),
    AuthRule(_m("POST"), re.compile(r"^/api/review/run/[^/]+/approve-all-slices$"), AuthTier.ADMIN, "approve-all-slices"),
    # --- 写入 / 触发（非高危）---
    AuthRule(_m("POST", "PUT", "PATCH", "DELETE"), re.compile(r"^/api/memory/"), AuthTier.WRITE, "memory-mutate"),
    AuthRule(_m("POST", "PUT", "PATCH", "DELETE"), re.compile(r"^/api/ad/bid/"), AuthTier.WRITE, "ad-bid-rules"),
    AuthRule(_m("POST"), re.compile(r"^/api/rpa/setup/"), AuthTier.WRITE, "rpa-setup"),
    AuthRule(_m("POST"), re.compile(r"^/api/rpa/test-ingest$"), AuthTier.WRITE, "rpa-test"),
    AuthRule(_m("POST"), re.compile(r"^/api/.+/start$"), AuthTier.WRITE, "worker-start"),
    AuthRule(_m("POST"), re.compile(r"^/api/.+/trigger$"), AuthTier.WRITE, "worker-trigger"),
    AuthRule(_m("POST"), re.compile(r"^/api/.+/poll$"), AuthTier.WRITE, "poll-trigger"),
    AuthRule(_m("POST"), re.compile(r"^/api/.+/scan$"), AuthTier.WRITE, "scan-trigger"),
    AuthRule(_m("POST"), re.compile(r"^/api/.+/run$"), AuthTier.WRITE, "generic-run"),
    AuthRule(_m("POST"), re.compile(r"^/api/.+/send$"), AuthTier.WRITE, "send-trigger"),
    AuthRule(_m("POST"), re.compile(r"^/api/workflow/runs/clear-completed$"), AuthTier.WRITE, "clear-completed-runs"),
    AuthRule(_m("POST"), re.compile(r"^/api/workflow/decisions/clear-pending$"), AuthTier.WRITE, "clear-pending"),
    AuthRule(_m("POST"), re.compile(r"^/api/workflow/decisions/"), AuthTier.WRITE, "workflow-decision"),
    AuthRule(_m("PATCH", "POST"), re.compile(r"^/api/publish/queue/"), AuthTier.WRITE, "queue-ops"),
    AuthRule(_m("POST"), re.compile(r"^/api/auth/logout$"), AuthTier.WRITE, "auth-logout"),
    AuthRule(_m("POST", "PUT", "PATCH", "DELETE"), re.compile(r"^/api/"), AuthTier.WRITE, "api-mutate-fallback"),
    AuthRule(_m("POST", "PUT", "PATCH", "DELETE"), re.compile(r"^/campaigns/"), AuthTier.WRITE, "campaign-mutate"),
    # --- WebSocket（Dashboard 实时）---
    AuthRule(_m("GET"), re.compile(r"^/ws/dashboard/"), AuthTier.READ, "dashboard-ws"),
    # --- 只读 API 兜底 ---
    AuthRule(_m("GET"), re.compile(r"^/api/"), AuthTier.READ, "api-read-fallback"),
    AuthRule(_m("GET"), re.compile(r"^/campaigns(?:/|$)"), AuthTier.READ, "campaign-read"),
)


def resolve_auth_tier(method: str, path: str) -> AuthTier:
    """解析请求对应的鉴权等级。"""
    m = method.upper()
    tier: AuthTier | None = None
    for rule in _AUTH_RULES:
        if m not in rule.methods and "*" not in rule.methods:
            continue
        if rule.pattern.match(path):
            tier = rule.tier
            break
    if tier is None:
        tier = AuthTier.READ if m == "GET" else AuthTier.WRITE
    return _apply_production_hardening(tier, path)


def _is_production() -> bool:
    import os

    return (os.environ.get("ENVIRONMENT") or "development").strip().lower() in ("production", "prod")


def _auth_enabled() -> bool:
    import os

    return os.environ.get("API_AUTH_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def _docs_public_in_production() -> bool:
    import os

    return os.environ.get("DOCS_PUBLIC_IN_PRODUCTION", "0").strip().lower() in ("1", "true", "yes", "on")


def _apply_production_hardening(tier: AuthTier, path: str) -> AuthTier:
    """生产 + 鉴权开启时，收紧文档/指标暴露面。"""
    if not _is_production() or not _auth_enabled():
        return tier
    if _docs_public_in_production():
        return tier
    if tier in (AuthTier.STATIC, AuthTier.PUBLIC) and (
        path.startswith(("/docs", "/redoc", "/openapi.json", "/metrics"))
    ):
        return AuthTier.READ
    return tier


def requires_api_key(tier: AuthTier) -> bool:
    return tier in _PROTECTED_TIERS


def requires_admin_key(tier: AuthTier, *, admin_key_configured: bool) -> bool:
    return tier == AuthTier.ADMIN and admin_key_configured


def tier_summary() -> dict[str, object]:
    counts: dict[str, int] = {}
    samples: dict[str, list[str]] = {}
    for rule in _AUTH_RULES:
        key = rule.tier.value
        counts[key] = counts.get(key, 0) + 1
        samples.setdefault(key, [])
        if len(samples[key]) < 5:
            samples[key].append(rule.note or rule.pattern.pattern)
    return {
        "tiers": [t.value for t in AuthTier],
        "protected_tiers": sorted(t.value for t in _PROTECTED_TIERS),
        "rule_count": len(_AUTH_RULES),
        "counts_by_tier": counts,
        "samples_by_tier": samples,
    }


def iter_rules() -> Iterable[AuthRule]:
    return iter(_AUTH_RULES)
