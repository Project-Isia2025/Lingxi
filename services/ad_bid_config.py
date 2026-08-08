"""投流调价规则持久化配置。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import bootstrap

DEFAULT_RULES: dict[str, Any] = {
    "enabled": True,
    "ctr_good": 0.02,
    "ctr_bad": 0.008,
    "cpc_max": 8.0,
    "roi_scale": 0.55,
    "roi_cut": 0.25,
    "budget_up_pct": 0.15,
    "budget_down_pct": 0.20,
    "min_budget": 30.0,
    "max_budget": 2000.0,
    "min_impressions": 500,
    "rules": [
        {"id": "low_ctr", "label": "CTR 过低降价", "enabled": True, "priority": 3},
        {"id": "high_cpc", "label": "CPC 过高降价", "enabled": True, "priority": 3},
        {"id": "low_roi", "label": "ROI 偏低降价", "enabled": True, "priority": 2},
        {"id": "good_roi_ctr", "label": "ROI+CTR 良好加价", "enabled": True, "priority": 2},
        {"id": "good_ctr", "label": "CTR 良好小幅加价", "enabled": True, "priority": 1},
    ],
}


def rules_path() -> Path:
    raw = (os.environ.get("AD_BID_RULES_PATH") or "data/ad_bid_rules.json").strip()
    p = Path(raw)
    if not p.is_absolute():
        p = bootstrap.project_root() / p
    return p


def load_bid_rules() -> dict[str, Any]:
    path = rules_path()
    if not path.is_file():
        save_bid_rules(DEFAULT_RULES)
        return dict(DEFAULT_RULES)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            merged = {**DEFAULT_RULES, **data}
            return merged
    except Exception:
        pass
    return dict(DEFAULT_RULES)


def save_bid_rules(rules: dict[str, Any]) -> dict[str, Any]:
    path = rules_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = {**DEFAULT_RULES, **(rules or {})}
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def apply_rules_to_env(rules: dict[str, Any]) -> None:
    """将 JSON 规则同步到环境变量供引擎读取。"""
    mapping = {
        "ctr_good": "AD_BID_CTR_GOOD",
        "ctr_bad": "AD_BID_CTR_BAD",
        "cpc_max": "AD_BID_CPC_MAX",
        "roi_scale": "AD_BID_ROI_SCALE",
        "roi_cut": "AD_BID_ROI_CUT",
        "budget_up_pct": "AD_BID_BUDGET_UP_PCT",
        "budget_down_pct": "AD_BID_BUDGET_DOWN_PCT",
        "min_budget": "AD_BID_MIN_BUDGET",
        "max_budget": "AD_BID_MAX_BUDGET",
    }
    for k, env_k in mapping.items():
        if k in rules:
            os.environ[env_k] = str(rules[k])
    if "enabled" in rules:
        os.environ["AD_AUTO_BID_ENABLED"] = "1" if rules["enabled"] else "0"
