"""Prometheus 指标暴露与刷新。"""
from __future__ import annotations

import logging
import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

log = logging.getLogger(__name__)

REQUESTS = Counter(
    "commerce_agent_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "commerce_agent_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
INFRA_HEALTH = Gauge("commerce_agent_infra_health", "Infrastructure health (1=ok)", ["service"])
WORKER_ENABLED = Gauge("commerce_agent_worker_enabled", "Background worker enabled flag", ["worker"])
WORKER_RUNNING = Gauge("commerce_agent_worker_running", "Background worker running flag", ["worker"])

_LAST_REFRESH_TS = 0.0
_REFRESH_INTERVAL_SEC = 15.0


def render_metrics() -> tuple[bytes, str]:
    refresh_dynamic_metrics()
    return generate_latest(), CONTENT_TYPE_LATEST


def record_request(*, method: str, endpoint: str, status: int, duration_sec: float) -> None:
    REQUESTS.labels(method=method, endpoint=endpoint, status=str(status)).inc()
    REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration_sec)


def set_infra_health(service: str, ok: bool) -> None:
    INFRA_HEALTH.labels(service=service).set(1 if ok else 0)


def refresh_dynamic_metrics() -> None:
    global _LAST_REFRESH_TS
    now = time.time()
    if now - _LAST_REFRESH_TS < _REFRESH_INTERVAL_SEC:
        return
    _LAST_REFRESH_TS = now

    _refresh_sqlite()
    _refresh_redis()
    _refresh_workers()


def _refresh_sqlite() -> None:
    try:
        from core.db import connect

        conn = connect()
        conn.execute("SELECT 1")
        conn.close()
        set_infra_health("sqlite", True)
    except Exception as exc:
        log.debug("metrics sqlite check failed: %s", exc)
        set_infra_health("sqlite", False)


def _refresh_redis() -> None:
    try:
        import redis

        client = redis.Redis(
            host=__import__("os").environ.get("REDIS_HOST", "localhost"),
            port=int(__import__("os").environ.get("REDIS_PORT", "6379")),
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        set_infra_health("redis", bool(client.ping()))
    except Exception as exc:
        log.debug("metrics redis check failed: %s", exc)
        set_infra_health("redis", False)


def _refresh_workers() -> None:
    probes = (
        ("publish_queue", "services.workers.publish_worker", "get_worker_status", "enabled", "running"),
        ("ad_poller", "services.workers.ad_scheduler", "get_poll_status", "enabled", "running"),
        ("perception_scheduler", "services.workers.perception_scheduler", "get_scheduler_status", "enabled", "running"),
        ("roi_report", "services.workers.report_scheduler", "get_report_scheduler_status", "enabled", "running"),
        ("alert_cleanup", "services.workers.alert_cleanup_scheduler", "get_alert_cleanup_status", "enabled", "running"),
        ("post_publish_monitor", "services.workers.post_publish_monitor_worker", "get_status", "enabled", "running"),
    )
    for name, mod_path, fn_name, enabled_key, running_key in probes:
        try:
            mod = __import__(mod_path, fromlist=[fn_name])
            status = getattr(mod, fn_name)()
            WORKER_ENABLED.labels(worker=name).set(1 if status.get(enabled_key) else 0)
            WORKER_RUNNING.labels(worker=name).set(1 if status.get(running_key) else 0)
        except Exception:
            WORKER_ENABLED.labels(worker=name).set(0)
            WORKER_RUNNING.labels(worker=name).set(0)
