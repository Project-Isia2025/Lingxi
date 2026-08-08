"""多 org 飞书/Webhook 分租户配置。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import bootstrap
import requests

from services.tenant import normalize_org_id


def org_webhooks_path() -> Path:
    raw = (os.environ.get("ORG_WEBHOOKS_PATH") or "data/org_webhooks.json").strip()
    p = Path(raw)
    if not p.is_absolute():
        p = bootstrap.project_root() / p
    return p


def load_org_webhooks() -> dict[str, Any]:
    path = org_webhooks_path()
    if not path.is_file():
        return {"orgs": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("orgs"), dict):
            return data
    except Exception:
        pass
    return {"orgs": {}}


def save_org_webhooks(data: dict[str, Any]) -> dict[str, Any]:
    path = org_webhooks_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def get_org_config(org_id: str) -> dict[str, Any]:
    oid = normalize_org_id(org_id)
    if not oid:
        return {}
    orgs = load_org_webhooks().get("orgs") or {}
    row = orgs.get(oid)
    return dict(row) if isinstance(row, dict) else {}


def upsert_org_config(org_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    oid = normalize_org_id(org_id)
    if not oid:
        return {"ok": False, "error": "org_id_required"}
    data = load_org_webhooks()
    orgs = dict(data.get("orgs") or {})
    base = dict(orgs.get(oid) or {})
    base.update({k: v for k, v in patch.items() if v is not None})
    orgs[oid] = base
    data["orgs"] = orgs
    save_org_webhooks(data)
    return {"ok": True, "org_id": oid, "config": base}


def _env_fallback(kind: str) -> str:
    if kind == "review":
        return (os.environ.get("REVIEW_FEISHU_WEBHOOK_URL") or os.environ.get("ROI_ALERT_WEBHOOK_URL") or "").strip()
    if kind in ("alert", "runbook"):
        return (os.environ.get("ROI_ALERT_WEBHOOK_URL") or os.environ.get("WEBHOOK_URL") or "").strip()
    return ""


def resolve_webhook(org_id: str = "", kind: str = "review") -> str:
    """kind: review | alert | runbook"""
    oid = normalize_org_id(org_id)
    key_map = {
        "review": "review_webhook_url",
        "alert": "alert_webhook_url",
        "runbook": "runbook_webhook_url",
    }
    key = key_map.get(kind, "alert_webhook_url")
    if oid:
        cfg = get_org_config(oid)
        if cfg.get("enabled") is False:
            return ""
        val = str(cfg.get(key) or "").strip()
        if val:
            return val
        fallback = str(cfg.get("alert_webhook_url") or cfg.get("review_webhook_url") or "").strip()
        if fallback:
            return fallback
    return _env_fallback(kind)


def resolve_review_base_url(org_id: str = "") -> str:
    oid = normalize_org_id(org_id)
    if oid:
        cfg = get_org_config(oid)
        val = str(cfg.get("review_base_url") or "").strip()
        if val:
            return val.rstrip("/")
    return (os.environ.get("REVIEW_BASE_URL") or "http://127.0.0.1:9200").rstrip("/")


def org_webhook_status(org_id: str = "") -> dict[str, Any]:
    oid = normalize_org_id(org_id)
    cfg = get_org_config(oid) if oid else {}
    review_url = resolve_webhook(oid, "review")
    alert_url = resolve_webhook(oid, "alert")
    runbook_url = resolve_webhook(oid, "runbook")
    base = resolve_review_base_url(oid)
    return {
        "ok": True,
        "org_id": oid or "(default)",
        "configured": bool(review_url or alert_url or runbook_url),
        "review_webhook": bool(review_url),
        "alert_webhook": bool(alert_url),
        "runbook_webhook": bool(runbook_url),
        "review_base_url": base,
        "callback_url": f"{base}/api/review/callback",
        "from_file": bool(cfg),
        "config": cfg,
        "live_ready": bool(review_url and base),
    }


def all_org_webhooks_status() -> dict[str, Any]:
    from services.org_catalog import list_org_ids

    orgs = load_org_webhooks().get("orgs") or {}
    known = sorted(set(list_org_ids()) | set(orgs.keys()))
    rows = [org_webhook_status(oid) for oid in known]
    default = org_webhook_status("")
    return {
        "ok": True,
        "default": default,
        "orgs": rows,
        "count": len(rows),
        "path": str(org_webhooks_path()),
    }


def send_webhook_message(*, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not url:
        return {"ok": False, "reason": "webhook_url_not_configured"}
    from services.roi_alert_format import format_webhook_bytes

    body_bytes = format_webhook_bytes(payload, url=url)
    try:
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            data=body_bytes,
            timeout=int(os.environ.get("ROI_ALERT_TIMEOUT_SEC", "15")),
        )
        ok = 200 <= resp.status_code < 300
        return {"ok": ok, "status_code": resp.status_code, "response": resp.text[:500]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


def send_org_webhook(*, org_id: str = "", kind: str = "alert", payload: dict[str, Any]) -> dict[str, Any]:
    url = resolve_webhook(org_id, kind)
    result = send_webhook_message(url=url, payload=payload)
    result["org_id"] = normalize_org_id(org_id) or "(default)"
    result["kind"] = kind
    result["url_configured"] = bool(url)
    return result
