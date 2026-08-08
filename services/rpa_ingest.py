"""影刀 / 八爪鱼等低代码 RPA Webhook 数据回写 → 感知层。"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import bootstrap


def _enabled() -> bool:
    return os.environ.get("RPA_INGEST_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def _store_path() -> Path:
    raw = (os.environ.get("RPA_INGEST_PATH") or "data/state/rpa_ingest.json").strip()
    p = Path(raw)
    if not p.is_absolute():
        p = bootstrap.project_root() / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _webhook_secret() -> str:
    return (
        os.environ.get("RPA_WEBHOOK_SECRET")
        or os.environ.get("YINGDAO_WEBHOOK_SECRET")
        or os.environ.get("OCTOPARSE_WEBHOOK_SECRET")
        or ""
    ).strip()


def verify_webhook_token(token: str = "") -> dict[str, Any]:
    secret = _webhook_secret()
    if not secret:
        env = (os.environ.get("ENVIRONMENT") or "development").strip().lower()
        allow_open = os.environ.get("RPA_WEBHOOK_ALLOW_OPEN", "0").strip().lower() in (
            "1", "true", "yes", "on",
        )
        if env in ("production", "prod"):
            return {"ok": False, "reason": "secret_required", "mode": "deny"}
        if allow_open or env in ("development", "dev", "test"):
            return {"ok": True, "mode": "open", "reason": "dev_open"}
        return {"ok": False, "reason": "secret_required", "mode": "deny"}
    if (token or "").strip() == secret:
        return {"ok": True, "mode": "authenticated"}
    return {"ok": False, "reason": "invalid_webhook_token"}


def _load_store() -> dict[str, Any]:
    path = _store_path()
    if not path.is_file():
        return {"records": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("records"), list):
            return raw
    except Exception:
        pass
    return {"records": []}


def _save_store(data: dict[str, Any]) -> None:
    path = _store_path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _mapping_path() -> Path:
    raw = (os.environ.get("RPA_FIELD_MAPPING_PATH") or "data/rpa_field_mapping.json").strip()
    p = Path(raw)
    if not p.is_absolute():
        p = bootstrap.project_root() / p
    return p


def load_field_mapping() -> dict[str, Any]:
    path = _mapping_path()
    if not path.is_file():
        example = bootstrap.project_root() / "data" / "rpa_field_mapping.example.json"
        if example.is_file():
            try:
                raw = json.loads(example.read_text(encoding="utf-8"))
                return raw if isinstance(raw, dict) else {}
            except Exception:
                return {}
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _first_value(raw: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def _extract_items_with_mapping(payload: dict[str, Any], source: str) -> list[dict[str, Any]]:
    cfg = load_field_mapping()
    src_cfg = (cfg.get("sources") or {}).get(source) or (cfg.get("sources") or {}).get("generic") or {}
    paths = src_cfg.get("items_path") or ["items", "data", "rows", "results", "videos", "products", "list"]
    if isinstance(paths, str):
        paths = [paths]
    for key in paths:
        val = payload.get(key)
        if isinstance(val, list) and val:
            return [x for x in val if isinstance(x, dict)]
    return _extract_items(payload)


def _map_item_fields(raw: dict[str, Any], *, source: str, platform: str) -> dict[str, Any]:
    cfg = load_field_mapping()
    src_cfg = (cfg.get("sources") or {}).get(source) or (cfg.get("sources") or {}).get("generic") or {}
    aliases: dict[str, list[str]] = src_cfg.get("field_aliases") or {}
    mapped: dict[str, Any] = dict(raw)
    for target, keys in aliases.items():
        if not isinstance(keys, list):
            continue
        val = _first_value(raw, keys)
        if val is not None:
            mapped[target] = val
    default_plat = str(src_cfg.get("platform_default") or platform or "douyin")
    return _normalize_item(mapped, platform=default_plat)


def _normalize_item(raw: dict[str, Any], *, platform: str) -> dict[str, Any]:
    title = str(raw.get("title") or raw.get("name") or raw.get("video_title") or raw.get("desc") or "")[:200]
    url = str(raw.get("url") or raw.get("link") or raw.get("video_url") or raw.get("share_url") or "")
    likes = raw.get("likes") or raw.get("digg_count") or raw.get("like_count") or 0
    comments = raw.get("comments") or raw.get("comment_count") or 0
    views = raw.get("views") or raw.get("play_count") or raw.get("view_count") or 0
    return {
        "title": title,
        "url": url,
        "likes": int(likes or 0),
        "comments": int(comments or 0),
        "views": int(views or 0),
        "platform": str(raw.get("platform") or platform or "douyin"),
        "source": "rpa_webhook",
        **{k: v for k, v in raw.items() if k not in ("title", "url", "likes", "comments", "views", "platform")},
    }


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("items", "data", "rows", "results", "videos", "products", "list"):
        val = payload.get(key)
        if isinstance(val, list) and val:
            return [x for x in val if isinstance(x, dict)]
    if payload.get("title") or payload.get("url"):
        return [payload]
    return []


def normalize_rpa_payload(payload: dict[str, Any], *, source: str = "generic") -> dict[str, Any]:
    """将影刀/八爪鱼/通用 Webhook 载荷规范化为感知层结构。"""
    src = (source or payload.get("source") or "generic").strip().lower()
    cfg = load_field_mapping()
    src_cfg = (cfg.get("sources") or {}).get(src) or (cfg.get("sources") or {}).get("generic") or {}

    platform = str(
        payload.get("platform") or payload.get("site") or payload.get("channel") or src_cfg.get("platform_default") or "douyin"
    ).strip().lower()

    keyword = str(payload.get("keyword") or payload.get("query") or payload.get("search") or "").strip()
    if not keyword:
        for kf in src_cfg.get("keyword_fields") or ["keyword", "query", "搜索词", "关键词"]:
            val = payload.get(kf)
            if val:
                keyword = str(val).strip()
                break

    task_id = str(payload.get("task_id") or payload.get("job_id") or payload.get("run_id") or "")
    items_raw = _extract_items_with_mapping(payload, src)
    items: list[dict[str, Any]] = []
    for x in items_raw:
        item = _map_item_fields(x, source=src, platform=platform)
        if item.get("title"):
            items.append(item)
    return {
        "source": src,
        "platform": platform,
        "keyword": keyword,
        "task_id": task_id,
        "items": items,
        "item_count": len(items),
    }


def ingest_rpa_webhook(
    payload: dict[str, Any],
    *,
    source: str = "generic",
    token: str = "",
) -> dict[str, Any]:
    auth = verify_webhook_token(token)
    if not auth.get("ok"):
        return {"ok": False, **auth}

    normalized = normalize_rpa_payload(payload, source=source)
    if not normalized.get("items"):
        return {
            "ok": False,
            "error": "no_items",
            "hint": "payload 需包含 items/data/rows 数组，或单条 title+url 记录",
            "normalized": normalized,
        }

    record = {
        "id": f"rpa-{uuid.uuid4().hex[:12]}",
        "source": normalized["source"],
        "platform": normalized["platform"],
        "keyword": normalized["keyword"],
        "task_id": normalized.get("task_id") or "",
        "item_count": normalized["item_count"],
        "items": normalized["items"],
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    store = _load_store()
    records = list(store.get("records") or [])
    records.insert(0, record)
    max_keep = int(os.environ.get("RPA_INGEST_MAX_RECORDS", "200") or 200)
    store["records"] = records[:max_keep]
    store["updated_at"] = record["received_at"]
    _save_store(store)

    return {
        "ok": True,
        "record_id": record["id"],
        "source": record["source"],
        "platform": record["platform"],
        "keyword": record["keyword"],
        "item_count": record["item_count"],
        "auth": auth.get("mode"),
    }


def list_rpa_records(*, limit: int = 20, platform: str = "", keyword: str = "") -> list[dict[str, Any]]:
    records = list(_load_store().get("records") or [])
    plat = (platform or "").strip().lower()
    key = (keyword or "").strip().lower()
    out: list[dict[str, Any]] = []
    for rec in records:
        if plat and str(rec.get("platform") or "").lower() != plat:
            continue
        if key and key not in str(rec.get("keyword") or "").lower():
            continue
        summary = {k: rec.get(k) for k in ("id", "source", "platform", "keyword", "task_id", "item_count", "received_at")}
        out.append(summary)
        if len(out) >= limit:
            break
    return out


def fetch_rpa_competitors(
    keyword: str,
    platform: str,
    *,
    limit: int = 15,
    max_age_hours: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """从 RPA Webhook 缓存读取竞品数据，供 perceive_market 优先使用。"""
    meta: dict[str, Any] = {"source": "rpa_webhook", "matched_records": 0}
    if not _enabled():
        meta["reason"] = "disabled"
        return [], meta

    try:
        max_age = float(
            max_age_hours
            if max_age_hours is not None
            else os.environ.get("RPA_INGEST_MAX_AGE_HOURS", "72") or 72
        )
    except ValueError:
        max_age = 72.0

    key = (keyword or "").strip().lower()
    plat = (platform or "douyin").strip().lower()
    now = datetime.now(timezone.utc)
    merged: list[dict[str, Any]] = []
    matched = 0

    for rec in _load_store().get("records") or []:
        rec_plat = str(rec.get("platform") or "").lower()
        if plat and rec_plat and rec_plat not in (plat, "all"):
            continue
        rec_key = str(rec.get("keyword") or "").lower()
        if key and rec_key and key not in rec_key and not any(t in rec_key for t in key.split() if len(t) >= 2):
            continue
        received = str(rec.get("received_at") or "")
        if received and max_age > 0:
            try:
                ts = datetime.fromisoformat(received.replace("Z", "+00:00"))
                age_h = (now - ts).total_seconds() / 3600.0
                if age_h > max_age:
                    continue
            except Exception:
                pass
        matched += 1
        for item in rec.get("items") or []:
            if isinstance(item, dict) and item.get("title"):
                merged.append(dict(item))

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in merged:
        sig = f"{item.get('title','')}|{item.get('url','')}"
        if sig in seen:
            continue
        seen.add(sig)
        deduped.append(item)
        if len(deduped) >= limit:
            break

    meta["matched_records"] = matched
    meta["item_count"] = len(deduped)
    meta["store_path"] = str(_store_path())
    return deduped, meta


def rpa_ingest_status() -> dict[str, Any]:
    store = _load_store()
    records = list(store.get("records") or [])
    secret = _webhook_secret()
    mapping_path = _mapping_path()
    return {
        "ok": True,
        "enabled": _enabled(),
        "auth_mode": "token" if secret else "open",
        "store_path": str(_store_path()),
        "mapping_path": str(mapping_path),
        "mapping_loaded": mapping_path.is_file() or (bootstrap.project_root() / "data" / "rpa_field_mapping.example.json").is_file(),
        "record_count": len(records),
        "latest_at": records[0].get("received_at") if records else "",
        "sources": sorted({str(r.get("source") or "generic") for r in records}),
    }


def init_field_mapping_file(*, force: bool = False) -> dict[str, Any]:
    """复制示例字段映射到 data/rpa_field_mapping.json（若不存在）。"""
    target = _mapping_path()
    example = bootstrap.project_root() / "data" / "rpa_field_mapping.example.json"
    if target.is_file() and not force:
        return {"ok": True, "created": False, "path": str(target), "reason": "already_exists"}
    if not example.is_file():
        return {"ok": False, "error": "example_missing", "path": str(example)}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    return {"ok": True, "created": True, "path": str(target)}


def build_rpa_integration_guide(*, base_url: str = "") -> dict[str, Any]:
    host = (base_url or os.environ.get("REVIEW_BASE_URL") or os.environ.get("PUBLIC_BASE_URL") or "http://127.0.0.1:9200").rstrip("/")
    secret = _webhook_secret()
    token_qs = f"?token={secret}" if secret else ""
    mapping = load_field_mapping()
    example_path = bootstrap.project_root() / "data" / "yingdao_webhook.example.json"
    example: dict[str, Any] = {}
    if example_path.is_file():
        try:
            example = json.loads(example_path.read_text(encoding="utf-8"))
        except Exception:
            example = {}
    yingdao_url = f"{host}/api/rpa/webhook/yingdao{token_qs}"
    body_json = json.dumps(example, ensure_ascii=False, indent=2) if example else "{}"
    return {
        "ok": True,
        "webhook_urls": {
            "yingdao": yingdao_url,
            "octoparse": f"{host}/api/rpa/webhook/octoparse{token_qs}",
            "generic": f"{host}/api/rpa/webhook{token_qs}",
        },
        "auth": {
            "mode": "token" if secret else "open",
            "header": "X-RPA-Webhook-Token",
            "query_param": "token",
            "env": "RPA_WEBHOOK_SECRET",
        },
        "field_mapping": {
            "config_path": str(_mapping_path()),
            "example_path": "data/rpa_field_mapping.example.json",
            "sources": list((mapping.get("sources") or {}).keys()),
        },
        "yingdao_http_step": mapping.get("yingdao_http_step_hint") or {},
        "yingdao_steps": [
            {
                "step": 1,
                "title": "在灵犀引擎配置密钥（可选但推荐）",
                "detail": "编辑 config/local.env，设置 RPA_WEBHOOK_SECRET=一串随机密码，保存后重启 api_server.py",
            },
            {
                "step": 2,
                "title": "复制字段映射文件",
                "detail": "将 data/rpa_field_mapping.example.json 复制为 data/rpa_field_mapping.json；若表格列名是中文（标题、点赞数），默认映射已可用",
                "action": "init_mapping",
            },
            {
                "step": 3,
                "title": "影刀流程末尾添加「HTTP 请求」指令",
                "detail": "在抓取循环结束后、流程最后一步插入 HTTP 请求",
                "fields": [
                    {"label": "请求方式", "value": "POST"},
                    {"label": "URL", "value": yingdao_url, "copy": True},
                    {"label": "Content-Type", "value": "application/json"},
                    {"label": "Header（若配置了密钥）", "value": f"X-RPA-Webhook-Token: {secret or '你的RPA_WEBHOOK_SECRET'}"},
                ],
            },
            {
                "step": 4,
                "title": "配置请求 Body（JSON）",
                "detail": "用影刀变量替换示例中的 keyword / items；items 为表格每一行组成的数组",
                "body_template": body_json,
                "copy_body": True,
            },
            {
                "step": 5,
                "title": "运行影刀并发一次测试",
                "detail": "在本页点击「发送测试数据」或运行 python scripts/acceptance_rpa_webhook.py，然后启动 AI 工作流验证感知是否用到 RPA 数据",
                "action": "test_webhook",
            },
        ],
        "payload_example": example,
        "payload_example_text": body_json,
        "verify": [
            f"GET {host}/api/rpa/status",
            f"POST {host}/api/rpa/webhook/yingdao",
            "python scripts/acceptance_rpa_webhook.py",
        ],
    }
