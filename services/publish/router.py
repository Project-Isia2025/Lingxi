"""多平台发布路由。"""
from __future__ import annotations

import os
from typing import Any

from services.publish import common as pub
from services.publish.creator_engine import PlatformPublishConfig, run_publish


def _douyin_cfg() -> PlatformPublishConfig:
    return PlatformPublishConfig(
        slug="douyin",
        upload_url=os.environ.get("DOUYIN_PUBLISH_UPLOAD_URL", "https://creator.douyin.com/creator-micro/content/upload"),
        manage_url=os.environ.get("DOUYIN_PUBLISH_MANAGE_URL", "https://creator.douyin.com/creator-micro/content/manage"),
        headless_env="DOUYIN_PUBLISH_HEADLESS",
        clipboard_origin="https://creator.douyin.com",
        title_max=30,
        login_signs=("扫码登录", "验证码登录", "创作者登录", "密码登录"),
        success_markers=("发布成功", "作品发布成功", "发布完成"),
        post_url_validator=lambda u: pub.public_url_validator(
            u, allow_hosts=("douyin.com", "iesdouyin.com"), path_hints=("/video/",)
        ),
    )


def _xhs_cfg() -> PlatformPublishConfig:
    return PlatformPublishConfig(
        slug="xiaohongshu",
        upload_url=os.environ.get(
            "XHS_PUBLISH_UPLOAD_URL", "https://creator.xiaohongshu.com/publish/publish?source=official"
        ),
        manage_url=os.environ.get("XHS_PUBLISH_MANAGE_URL", "https://creator.xiaohongshu.com/new/note-manager"),
        headless_env="XHS_PUBLISH_HEADLESS",
        clipboard_origin="https://creator.xiaohongshu.com",
        title_max=20,
        login_signs=("扫码登录", "验证码登录", "请登录", "手机号登录"),
        success_markers=("发布成功", "笔记发布成功", "发布完成", "已发布"),
        post_url_validator=lambda u: pub.public_url_validator(
            u,
            allow_hosts=("xiaohongshu.com", "xhslink.com"),
            path_hints=("/explore/", "/discovery/item/", "/item/"),
        ),
        fill_mode="xhs_form",
    )


def _shipinhao_cfg() -> PlatformPublishConfig:
    return PlatformPublishConfig(
        slug="shipinhao",
        upload_url=os.environ.get(
            "SHIPINHAO_PUBLISH_UPLOAD_URL", "https://channels.weixin.qq.com/platform/post/create"
        ),
        manage_url=os.environ.get("SHIPINHAO_PUBLISH_MANAGE_URL", "https://channels.weixin.qq.com/platform/post/list"),
        headless_env="SHIPINHAO_PUBLISH_HEADLESS",
        clipboard_origin="https://channels.weixin.qq.com",
        title_max=20,
        login_signs=("微信扫码", "登录", "请登录"),
        success_markers=("发表成功", "发布成功", "已发布"),
        post_url_validator=lambda u: pub.public_url_validator(u, allow_hosts=("weixin.qq.com",), path_hints=()),
        fill_mode="title_desc",
    )


PLATFORM_CONFIGS = {
    "douyin": _douyin_cfg,
    "xiaohongshu": _xhs_cfg,
    "xhs": _xhs_cfg,
    "shipinhao": _shipinhao_cfg,
    "weixin_channels": _shipinhao_cfg,
}


def supported_platforms() -> list[str]:
    return ["douyin", "xiaohongshu", "shipinhao"]


def health(platform: str) -> dict[str, Any]:
    plat = (platform or "").strip().lower()
    if plat == "xhs":
        plat = "xiaohongshu"
    storage = pub.resolve_storage(plat)
    return {
        "platform": plat,
        "enabled": pub.publish_enabled(plat),
        "storage_state": storage or None,
        "storage_exists": bool(storage),
        "ready": bool(storage) and pub.publish_enabled(plat),
    }


def publish_to_platform(
    platform: str,
    *,
    video_path: str,
    script: str,
    title: str = "",
    tags: list[str] | None = None,
    dry_run: bool = False,
    account_id: str = "default",
    run_id: str = "",
    keyword: str = "",
) -> dict[str, Any]:
    plat = (platform or "douyin").strip().lower()
    if plat == "xhs":
        plat = "xiaohongshu"
    if plat not in PLATFORM_CONFIGS:
        return {"success": False, "error": f"unsupported_platform:{plat}"}

    metadata = pub.build_metadata(script=script, title=title, tags=tags)

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "platform": plat,
            "metadata": metadata,
            "video_path": video_path,
        }

    ok, err = pub.validate_video_path(video_path)
    if not ok:
        return {"success": False, "error": err, "platform": plat}

    if not pub.publish_enabled(plat):
        return {"success": False, "error": "publish_disabled", "platform": plat}

    can, quota_msg = pub.check_publish_quota(plat, account_id=account_id)
    if not can:
        return {"success": False, "error": "quota_exceeded", "message": quota_msg, "platform": plat}

    storage = pub.resolve_storage(plat, account_id=account_id)
    cfg_fn = PLATFORM_CONFIGS[plat]
    timeout = int(os.environ.get("PUBLISH_TIMEOUT_SEC", "240"))
    result = run_publish(cfg_fn(), video_path=video_path, metadata=metadata, storage_state=storage, timeout_sec=timeout)

    if result.get("success"):
        pub.mark_published(plat, account_id=account_id)
        from core.storage import append_publish_log

        append_publish_log(
            platform=plat,
            video_path=video_path,
            post_url=str(result.get("post_url") or ""),
            metadata=metadata,
        )
        try:
            from services.publish_feedback import apply_publish_success_feedback

            result["roi_feedback"] = apply_publish_success_feedback(
                platform=plat,
                script=script,
                title=title or metadata.get("title", ""),
                post_url=str(result.get("post_url") or ""),
                run_id=run_id,
                account_id=account_id,
                keyword=keyword,
            )
        except Exception as exc:
            result["roi_feedback_error"] = str(exc)[:200]
    return result


def publish_multi(
    platforms: list[str],
    *,
    video_path: str,
    script: str,
    title: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    results = []
    for p in platforms:
        results.append(
            publish_to_platform(
                p,
                video_path=video_path,
                script=script,
                title=title,
                dry_run=dry_run,
            )
        )
    ok_n = sum(1 for r in results if r.get("success"))
    return {"ok": ok_n > 0, "success_count": ok_n, "results": results}
