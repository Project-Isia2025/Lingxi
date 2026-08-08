"""运维 Dashboard 数据聚合 + 生产 E2E 联调指南。"""
from __future__ import annotations

from typing import Any

E2E_GUIDE_PHASES: list[dict[str, Any]] = [
    {
        "phase": "1. 环境与自启",
        "steps": [
            {
                "id": "env",
                "title": "复制并编辑 local.env",
                "command": "copy config\\local.env.example config\\local.env",
                "verify": "config/local.env 存在且 REVIEW_BASE_URL 已设置",
            },
            {
                "id": "api",
                "title": "启动 API 或安装自启",
                "command": "python api_server.py",
                "alt_command": "powershell -ExecutionPolicy Bypass -File scripts/windows/install_service.ps1",
                "verify": "GET /api/health 返回 ok=true",
            },
        ],
    },
    {
        "phase": "2. 登录态导出",
        "steps": [
            {
                "id": "storage_check",
                "title": "检查登录态缺失项",
                "command": "python scripts/export_storage_wizard.py --check",
                "verify": "douyin_creator 显示 valid=true",
            },
            {
                "id": "storage_export",
                "title": "导出抖音创作者中心登录态",
                "command": "python scripts/export_storage_wizard.py --export douyin_creator",
                "verify": "data/state/douyin_creator_storage.json 有效",
            },
        ],
    },
    {
        "phase": "3. 公网回调",
        "steps": [
            {
                "id": "tunnel",
                "title": "启动完整 Docker 栈（含隧道）",
                "command": "python scripts/docker_up.py --stack full --build",
                "verify": "docker logs ai-agent-matrix-tunnel 出现 trycloudflare URL",
            },
            {
                "id": "feishu",
                "title": "配置飞书 Webhook 与回调",
                "command": "REVIEW_BASE_URL=<公网URL> REVIEW_FEISHU_WEBHOOK_URL=<Webhook>",
                "verify": "GET /api/review/feishu/status live_ready=true",
            },
        ],
    },
    {
        "phase": "4. 发布联调",
        "steps": [
            {
                "id": "publish_probe",
                "title": "上传页 smoke 探测（不发布）",
                "command": "python scripts/acceptance_publish_smoke.py --live-probe --headed",
                "verify": "probe=true success",
            },
            {
                "id": "publish_submit",
                "title": "真实单条发布（谨慎）",
                "command": "python scripts/acceptance_publish_smoke.py --submit --confirm --headed",
                "verify": "submitted=true，创作者中心可见新作品",
            },
        ],
    },
    {
        "phase": "5. 监控与下架",
        "steps": [
            {
                "id": "monitor_e2e",
                "title": "完播监控 dry-run 验收",
                "command": "python scripts/acceptance_monitor_e2e.py",
                "verify": "8/8 步骤通过",
            },
            {
                "id": "monitor_live",
                "title": "启用真实下架（可选，谨慎）",
                "command": "TAKEDOWN_ENABLED=1",
                "verify": "低指标作品触发 creator_center 下架",
            },
        ],
    },
    {
        "phase": "6. 一键验收",
        "steps": [
            {
                "id": "acceptance_all",
                "title": "全链路一键验收",
                "command": "python scripts/acceptance_all.py --quick",
                "verify": "11/11 阶段通过（docker 可 skip）",
            },
            {
                "id": "live_runbook",
                "title": "生产联调 Runbook",
                "command": "python scripts/acceptance_live_runbook.py --live",
                "verify": "全部 required 步骤 ok",
            },
        ],
    },
]


def _score_runbook(runbook: dict[str, Any]) -> dict[str, Any]:
    steps = runbook.get("steps") or []
    required = [s for s in steps if not s.get("skipped")]
    passed = sum(1 for s in required if s.get("ok"))
    return {
        "passed": passed,
        "total": len(required),
        "ok": passed == len(required) if required else True,
        "live": runbook.get("live"),
    }


def _org_queue_summary(*, org_id: str = "", limit: int = 20) -> dict[str, Any]:
    from services.publish_queue_dashboard import build_publish_queue_dashboard
    from services.tenant import normalize_org_id

    oid = normalize_org_id(org_id)
    dash = build_publish_queue_dashboard(limit=limit, org_id=oid)
    stats = dash.get("stats") or {}
    return {
        "org_id": oid or "(all)",
        "queued_due_now": stats.get("queued_due_now", 0),
        "queued_scheduled": stats.get("queued_scheduled", 0),
        "total": stats.get("total", 0),
        "unique_runs": stats.get("unique_runs", 0),
        "worker_enabled": bool((dash.get("worker") or {}).get("enabled")),
    }


def _org_monitor_summary(*, org_id: str = "") -> dict[str, Any]:
    from core.storage import list_post_monitors
    from services.tenant import filter_by_org, normalize_org_id

    oid = normalize_org_id(org_id)
    pending = filter_by_org(list_post_monitors(status="pending", limit=100), oid)
    ok_rows = filter_by_org(list_post_monitors(status="ok", limit=50), oid)
    takedown = filter_by_org(list_post_monitors(status="takedown_reedit", limit=50), oid)
    return {
        "org_id": oid or "(all)",
        "pending": len(pending),
        "ok": len(ok_rows),
        "takedown_reedit": len(takedown),
    }


def _build_operator_view(
    *,
    rt: dict[str, Any],
    storage: dict[str, Any],
    workers: dict[str, Any],
    org_queue: dict[str, Any],
    org_monitor: dict[str, Any],
) -> dict[str, Any]:
    """面向非技术运营者的简化状态视图。"""
    platform_names = {
        "douyin_creator": "抖音",
        "xhs_creator": "小红书",
        "shipinhao_creator": "视频号",
    }
    publish_keys = ("douyin_creator", "xhs_creator", "shipinhao_creator")
    targets = {t.get("id"): t for t in (storage.get("targets") or []) if isinstance(t, dict)}
    logged_in = [platform_names[k] for k in publish_keys if targets.get(k, {}).get("ready")]
    not_logged_in = [platform_names[k] for k in publish_keys if not targets.get(k, {}).get("ready")]

    pub = workers.get("publish_queue") or {}
    mon = workers.get("post_publish_monitor") or {}
    publish_ok = bool(pub.get("active"))
    monitor_ok = bool(mon.get("active"))
    login_ok = len(not_logged_in) == 0

    items: list[dict[str, Any]] = [
        {
            "id": "publish",
            "icon": "📤",
            "title": "自动发布助手",
            "ok": publish_ok,
            "status_text": "已开启" if publish_ok else "未开启",
            "description": "开启后，系统会自动把做好的视频发布到平台。"
            if publish_ok
            else "当前未开启，视频会积压在「待发布内容」里，需要手动处理。",
            "action": None if publish_ok else "start_publish",
            "action_label": "开启自动发布",
        },
        {
            "id": "monitor",
            "icon": "👀",
            "title": "内容效果监控",
            "ok": monitor_ok,
            "status_text": "已开启" if monitor_ok else "未开启",
            "description": "开启后，系统会定期检查已发视频的数据表现。"
            if monitor_ok
            else "当前未开启，已发布视频的表现不会被自动跟踪。",
            "action": None if monitor_ok else "start_monitor",
            "action_label": "开启内容监控",
        },
        {
            "id": "login",
            "icon": "🔑",
            "title": "平台账号登录",
            "ok": login_ok,
            "status_text": f"已登录 {len(logged_in)}/3 个平台" if logged_in else "尚未登录",
            "description": (
                f"已就绪：{'、'.join(logged_in)}"
                if logged_in and login_ok
                else (
                    f"已就绪：{'、'.join(logged_in)}；"
                    f"还需登录：{'、'.join(not_logged_in)}"
                    if logged_in
                    else f"需要在电脑上登录：{'、'.join(not_logged_in)}"
                )
            ),
            "action": None,
            "action_label": "",
            "help": "这一步需要技术人员在浏览器登录抖音、小红书、视频号的创作者中心，完成后刷新本页即可。",
        },
        {
            "id": "queue",
            "icon": "📋",
            "title": "待发布内容",
            "ok": int(org_queue.get("total") or 0) == 0,
            "status_text": f"共 {int(org_queue.get('total') or 0)} 条",
            "description": "没有等待发布的内容，一切正常。"
            if int(org_queue.get("total") or 0) == 0
            else f"有 {int(org_queue.get('total') or 0)} 条内容等待发布，建议打开「待发布内容」查看。",
            "action": "open_queue",
            "action_label": "查看待发布",
            "always_show_action": True,
        },
    ]

    must_fix = [i for i in items if i["id"] in ("publish", "monitor", "login") and not i["ok"]]
    notice = [i for i in items if i["id"] == "queue" and not i["ok"]]

    if not must_fix and not notice:
        overall_title = "一切正常，可以放心使用"
        overall_level = "ok"
        overall_hint = "系统各项功能运行正常。您只需在首页发起推广，其余交给系统自动处理。"
    elif must_fix:
        overall_title = f"有 {len(must_fix)} 项需要处理"
        overall_level = "warn"
        overall_hint = "请按下方提示逐项处理；看不懂的项请联系技术人员协助。"
    else:
        overall_title = "系统正常，有待发布内容"
        overall_level = "ok"
        overall_hint = "系统功能正常，建议查看待发布内容列表。"

    return {
        "overall_ok": not must_fix,
        "overall_title": overall_title,
        "overall_level": overall_level,
        "overall_hint": overall_hint,
        "items": items,
        "pending_monitor": int(org_monitor.get("pending") or 0),
        "updated_hint": "数据约每分钟自动刷新，也可手动点刷新。",
    }


def build_runtime_dashboard(*, platform: str = "douyin", org_id: str = "") -> dict[str, Any]:
    from services.live_runbook import build_live_runbook
    from services.monitor_readiness import monitor_readiness_status
    from services.org_catalog import org_catalog_status
    from services.runtime_status import runtime_status
    from services.storage_state_wizard import all_storage_status
    from services.tenant import normalize_org_id, org_isolation_enabled

    oid = normalize_org_id(org_id)
    rt = runtime_status()
    storage = all_storage_status()
    monitor = monitor_readiness_status(platform=platform)
    runbook = build_live_runbook(live=False, platform=platform)
    rb_score = _score_runbook(runbook)
    org_catalog = org_catalog_status()
    org_queue = _org_queue_summary(org_id=oid)
    org_monitor = _org_monitor_summary(org_id=oid)
    from services.org_webhook_config import org_webhook_status

    org_webhook = org_webhook_status(oid)
    from services.runbook_alert import runbook_alert_enabled, runbook_alert_min_failures

    workers = rt.get("workers") or {}
    cards = [
        {
            "key": "api",
            "label": "API 服务",
            "value": "在线" if rt.get("api_live") else "离线",
            "ok": bool(rt.get("api_live")),
            "hint": rt.get("hints", {}).get("start_api"),
        },
        {
            "key": "publish_worker",
            "label": "发布 Worker",
            "value": "运行中" if (workers.get("publish_queue") or {}).get("active") else "未运行",
            "ok": bool((workers.get("publish_queue") or {}).get("active")),
        },
        {
            "key": "monitor_worker",
            "label": "监控 Worker",
            "value": "运行中" if (workers.get("post_publish_monitor") or {}).get("active") else "未运行",
            "ok": bool((workers.get("post_publish_monitor") or {}).get("active")),
        },
        {
            "key": "storage",
            "label": "登录态",
            "value": f"{len(storage.get('ready') or [])}/{len(storage.get('targets') or [])} 就绪",
            "ok": bool(storage.get("publish_ready")) or len(storage.get("missing") or []) == 0,
        },
        {
            "key": "runbook",
            "label": "联调 Runbook",
            "value": f"{rb_score.get('passed')}/{rb_score.get('total')}",
            "ok": rb_score.get("ok"),
        },
        {
            "key": "autostart",
            "label": "开机自启",
            "value": "已安装" if (rt.get("autostart") or {}).get("installed") or (rt.get("autostart") or {}).get("template_ready") else "未配置",
            "ok": bool((rt.get("autostart") or {}).get("installed") or (rt.get("autostart") or {}).get("template_ready")),
        },
    ]
    if org_isolation_enabled():
        cards.append({
            "key": "org_queue",
            "label": f"队列({oid or '全部'})",
            "value": f"到期 {org_queue.get('queued_due_now', 0)} / 共 {org_queue.get('total', 0)}",
            "ok": True,
        })
        cards.append({
            "key": "org_monitor",
            "label": f"监控({oid or '全部'})",
            "value": f"待轮询 {org_monitor.get('pending', 0)}",
            "ok": org_monitor.get("pending", 0) >= 0,
        })
        cards.append({
            "key": "org_webhook",
            "label": f"Webhook({oid or 'default'})",
            "value": "已配置" if org_webhook.get("configured") else "未配置",
            "ok": bool(org_webhook.get("configured")),
        })

    checklist = []
    for step in runbook.get("steps") or []:
        checklist.append({
            "step": step.get("step"),
            "ok": bool(step.get("ok")),
            "skipped": bool(step.get("skipped")),
            "detail": step.get("detail") or "",
        })

    operator = _build_operator_view(
        rt=rt,
        storage=storage,
        workers=workers,
        org_queue=org_queue,
        org_monitor=org_monitor,
    )

    return {
        "ok": True,
        "platform": platform,
        "org_id": oid,
        "org_isolation": org_isolation_enabled(),
        "org_catalog": org_catalog,
        "org_queue": org_queue,
        "org_monitor": org_monitor,
        "org_webhook": org_webhook,
        "runbook_alert": {
            "enabled": runbook_alert_enabled(),
            "min_failures": runbook_alert_min_failures(),
        },
        "cards": cards,
        "runtime": rt,
        "storage": storage,
        "monitor": monitor,
        "runbook_score": rb_score,
        "runbook_checklist": checklist,
        "guide": E2E_GUIDE_PHASES,
        "operator": operator,
        "links": {
            "runtime_dashboard": "/dashboard/runtime",
            "runbook_api": "/api/runtime/runbook",
            "publish_queue": "/dashboard/publish-queue",
            "docs": "/docs",
            "advanced": "/dashboard/runtime/advanced",
        },
    }
