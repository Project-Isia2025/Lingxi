"""生产环境真实联调 Runbook（检查清单 + 可选 live 步骤）。"""
from __future__ import annotations

from typing import Any


def build_live_runbook(*, live: bool = False, platform: str = "douyin", org_id: str = "", notify: bool = False) -> dict[str, Any]:
    """汇总发布/监控/飞书/隧道/运行时就绪项，生成有序检查清单。"""
    steps: list[dict[str, Any]] = []

    from services.runtime_status import runtime_status

    rt = runtime_status()
    steps.append({
        "step": "runtime_status",
        "ok": rt.get("ok"),
        "detail": f"api_live={rt.get('api_live')} platform={rt.get('platform')}",
        "result": rt,
    })

    from services.storage_state_wizard import all_storage_status

    storage = all_storage_status()
    missing = storage.get("missing") or []
    steps.append({
        "step": "storage_wizard",
        "ok": len(missing) == 0 or not live,
        "detail": f"missing={missing[:3]}",
        "result": storage,
    })

    from services.publish_readiness import all_publish_readiness, platform_readiness

    pub = all_publish_readiness()
    plat = platform_readiness(platform)
    steps.append({
        "step": "publish_readiness",
        "ok": bool(pub.get("ok")),
        "detail": f"ready={pub.get('ready')} target={platform} ready={plat.get('ready')}",
        "result": {"all": pub, "platform": plat},
    })

    from services.tunnel import tunnel_status

    tunnel = tunnel_status()
    steps.append({
        "step": "tunnel_callback",
        "ok": True,
        "detail": f"needs_tunnel={tunnel.get('needs_tunnel')} callback={tunnel.get('callback_url', '')[:60]}",
        "result": tunnel,
    })

    from services.feishu_review_status import feishu_review_status

    feishu = feishu_review_status(org_id=org_id)
    steps.append({
        "step": "feishu_review",
        "ok": bool(feishu.get("ok")) or not live,
        "detail": f"webhook={'set' if feishu.get('webhook_configured') else 'missing'}",
        "result": feishu,
    })

    from services.monitor_readiness import monitor_readiness_status

    monitor = monitor_readiness_status(platform=platform)
    steps.append({
        "step": "monitor_readiness",
        "ok": bool(monitor.get("monitor_enabled")),
        "detail": f"takedown_dry_run={monitor.get('takedown_dry_run')}",
        "result": monitor,
    })

    from services.deploy_status import deploy_manifest_status

    deploy = deploy_manifest_status()
    steps.append({
        "step": "deploy_templates",
        "ok": bool(deploy.get("ok")),
        "detail": f"docker={deploy.get('docker_prod_ready')} k8s={deploy.get('k8s_ready')} helm={deploy.get('helm_ready')}",
        "result": deploy,
    })

    if live:
        from services.publish_monitor_chain import run_publish_monitor_chain

        chain = run_publish_monitor_chain(live=True, platform=platform)
        steps.append({
            "step": "publish_monitor_chain",
            "ok": bool(chain.get("ok")),
            "detail": f"{chain.get('passed')}/{chain.get('total')} live",
            "result": chain,
        })
    else:
        from services.publish_monitor_chain import run_publish_monitor_chain

        chain = run_publish_monitor_chain(live=False, platform=platform)
        steps.append({
            "step": "publish_monitor_chain_dry",
            "ok": bool(chain.get("ok")),
            "detail": f"{chain.get('passed')}/{chain.get('total')} dry-run",
            "result": chain,
        })
        steps.append({
            "step": "live_hint",
            "ok": True,
            "skipped": True,
            "detail": "追加 --live 执行真实上传探测与发布→监控链路",
            "result": {},
        })

    passed = sum(1 for s in steps if s.get("ok"))
    required = [s for s in steps if not s.get("skipped")]
    req_passed = sum(1 for s in required if s.get("ok"))
    result = {
        "ok": req_passed == len(required),
        "passed": passed,
        "total": len(steps),
        "live": live,
        "platform": platform,
        "org_id": org_id,
        "steps": steps,
    }
    if notify:
        from services.runbook_alert import dispatch_runbook_alert

        result["alert"] = dispatch_runbook_alert(
            runbook=result,
            org_id=org_id,
            platform=platform,
            dry_run=not live,
        )
    return result
