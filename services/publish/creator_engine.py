"""创作者中心 Playwright 自动发布引擎。"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from services.publish import common as pub
from services.publish.playwright_util import playwright_sync_context


@dataclass(frozen=True)
class PlatformPublishConfig:
    slug: str
    upload_url: str
    manage_url: str
    headless_env: str
    clipboard_origin: str
    title_max: int
    login_signs: tuple[str, ...]
    success_markers: tuple[str, ...]
    post_url_validator: Callable[[str], str]
    fill_mode: str = "title_desc"
    file_selectors: tuple[str, ...] = ('input[type="file"]', 'input[accept*="video"]')
    submit_selectors: tuple[str, ...] = ('button:has-text("发布")', 'button:has-text("立即发布")')


def _selector_list(env: str, defaults: tuple[str, ...]) -> list[str]:
    raw = (os.environ.get(env) or "").strip()
    if raw:
        return [s.strip() for s in raw.split("||") if s.strip()]
    return list(defaults)


def _click_first(page, selectors: list[str], *, timeout_ms: int = 10000) -> tuple[bool, str]:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0:
                loc.scroll_into_view_if_needed(timeout=timeout_ms)
                loc.click(timeout=timeout_ms)
                return True, sel
        except Exception:
            continue
    return False, ""


def _fill_first(page, selectors: list[str], text: str, *, timeout_ms: int = 15000) -> tuple[bool, str]:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() <= 0:
                continue
            loc.scroll_into_view_if_needed(timeout=timeout_ms)
            loc.click(timeout=timeout_ms)
            try:
                loc.fill(text, timeout=timeout_ms)
                return True, sel
            except Exception:
                loc.evaluate(
                    """(el, t) => {
                        el.focus();
                        if ('value' in el) el.value = t;
                        else el.textContent = t;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                    }""",
                    text,
                )
                return True, f"{sel}:js"
        except Exception:
            continue
    return False, ""


def _desc_text(metadata: dict[str, Any]) -> str:
    tags = [str(x).strip().lstrip("#") for x in (metadata.get("tags") or []) if str(x).strip()]
    parts = []
    if tags:
        parts.append(" ".join(f"#{t}" for t in tags[:8]))
    disc = str(metadata.get("ai_disclosure_text") or "").strip()
    if disc:
        parts.append(disc)
    return "\n".join(parts)[:500]


def _fill_metadata(page, metadata: dict[str, Any], cfg: PlatformPublishConfig) -> tuple[bool, str]:
    title = str(metadata.get("title") or "AI口播")[: cfg.title_max]
    desc = _desc_text(metadata)
    tags = [str(x).strip().lstrip("#") for x in (metadata.get("tags") or []) if str(x).strip()]

    if cfg.fill_mode == "xhs_form":
        title_sels = _selector_list("XHS_PUBLISH_TITLE_SELECTORS", ('input.d-text', 'input[placeholder*="标题"]'))
        ok, sel = _fill_first(page, title_sels, title[:20])
        if not ok:
            return False, ""
        desc_sels = _selector_list("XHS_PUBLISH_DESC_SELECTORS", ('#quillEditor div', '[contenteditable="true"]'))
        body = f"{title}\n{desc}".strip()[:900]
        _fill_first(page, desc_sels, body)
        for tag in tags[:5]:
            ok_tag, tag_sel = _fill_first(page, desc_sels, f"#{tag}")
            if ok_tag:
                try:
                    page.locator(tag_sel.split(":js")[0]).first.press("Enter")
                except Exception:
                    pass
                page.wait_for_timeout(400)
        return True, sel

    title_sels = _selector_list(
        f"{cfg.slug.upper()}_PUBLISH_TITLE_SELECTORS",
        ('input[placeholder*="标题"]', 'textarea[placeholder*="标题"]'),
    )
    ok, sel = _fill_first(page, title_sels, title)
    if not ok:
        return False, ""
    if desc:
        desc_sels = _selector_list(
            f"{cfg.slug.upper()}_PUBLISH_DESC_SELECTORS",
            ('textarea[placeholder*="简介"]', 'textarea[placeholder*="描述"]', '[contenteditable="true"]'),
        )
        _fill_first(page, desc_sels, desc)
    return True, sel


def _wait_ready(page, cfg: PlatformPublishConfig, timeout_ms: int) -> bool:
    deadline = time.time() + max(10, timeout_ms / 1000)
    sels = _selector_list(
        f"{cfg.slug.upper()}_PUBLISH_READY_SELECTORS",
        ('input[placeholder*="标题"]', 'input[type="file"]'),
    )
    while time.time() < deadline:
        for sel in sels:
            try:
                if page.locator(sel).count() > 0:
                    return True
            except Exception:
                pass
        page.wait_for_timeout(1200)
    return False


def _collect_links(page) -> list[str]:
    try:
        links = page.evaluate(
            """() => Array.from(document.querySelectorAll('a[href]'))
                .map(a => String(a.href||'').trim()).filter(u => /^https?:/.test(u)).slice(0,30)"""
        )
        return list(links) if isinstance(links, list) else []
    except Exception:
        return []


def run_publish(
    cfg: PlatformPublishConfig,
    *,
    video_path: str,
    metadata: dict[str, Any],
    storage_state: str,
    timeout_sec: int = 240,
    probe_only: bool = False,
) -> dict[str, Any]:
    local = Path(video_path)
    ok, err = pub.validate_video_path(str(local))
    if not ok:
        return {"success": False, "error": err, "platform": cfg.slug}

    if not storage_state or not Path(storage_state).is_file():
        return {"success": False, "error": "storage_state_missing", "platform": cfg.slug}

    submit_sels = _selector_list(f"{cfg.slug.upper()}_PUBLISH_SUBMIT_SELECTORS", cfg.submit_selectors)
    file_sels = _selector_list(f"{cfg.slug.upper()}_PUBLISH_FILE_SELECTORS", cfg.file_selectors)
    headless = pub.env_truthy(cfg.headless_env, "1")

    try:
        with playwright_sync_context() as p:
            launch_kw: dict[str, Any] = {"headless": headless}
            channel = (os.environ.get("PUBLISH_PLAYWRIGHT_CHANNEL") or "").strip()
            if channel:
                launch_kw["channel"] = channel
            browser = p.chromium.launch(**launch_kw)
            try:
                context = browser.new_context(
                    storage_state=str(Path(storage_state).resolve()),
                    locale="zh-CN",
                    viewport={"width": 1440, "height": 900},
                    user_agent=pub.DEFAULT_UA,
                )
                try:
                    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=cfg.clipboard_origin)
                except Exception:
                    pass
                page = context.new_page()
                page.goto(cfg.upload_url, wait_until="domcontentloaded", timeout=120_000)
                page.wait_for_timeout(int(os.environ.get("PUBLISH_POST_LOAD_WAIT_MS", "8000")))
                body = page.locator("body").inner_text(timeout=15000)
                if any(s in body for s in cfg.login_signs):
                    return {"success": False, "error": "creator_login_required", "platform": cfg.slug}

                uploaded = False
                upload_sel = ""
                for sel in file_sels:
                    try:
                        loc = page.locator(sel).first
                        if loc.count() > 0:
                            loc.set_input_files(str(local.resolve()), timeout=30000)
                            uploaded = True
                            upload_sel = sel
                            break
                    except Exception:
                        continue
                if not uploaded:
                    return {"success": False, "error": "upload_input_not_found", "platform": cfg.slug}

                if not _wait_ready(page, cfg, int(timeout_sec * 1000)):
                    return {"success": False, "error": "upload_not_ready", "platform": cfg.slug}

                title_ok, title_sel = _fill_metadata(page, metadata, cfg)
                if not title_ok:
                    return {"success": False, "error": "title_input_not_found", "platform": cfg.slug}

                if probe_only:
                    return {
                        "success": True,
                        "probe": True,
                        "platform": cfg.slug,
                        "upload_selector": upload_sel,
                        "title_selector": title_sel,
                        "page_url": page.url,
                        "message": "上传页探测成功（未点击发布）",
                    }

                clicked, pub_sel = _click_first(page, submit_sels, timeout_ms=12000)
                if not clicked:
                    return {"success": False, "error": "publish_button_not_found", "platform": cfg.slug}

                deadline = time.time() + max(30, timeout_sec)
                post_url = ""
                confirmed = False
                while time.time() < deadline:
                    page.wait_for_timeout(1500)
                    try:
                        body2 = page.locator("body").inner_text(timeout=10000)
                    except Exception:
                        body2 = ""
                    if any(m in body2 for m in cfg.success_markers):
                        confirmed = True
                    for link in _collect_links(page):
                        val = cfg.post_url_validator(link)
                        if val:
                            post_url = val
                            confirmed = True
                            break
                    if confirmed and post_url:
                        break

                if not confirmed:
                    try:
                        page.goto(cfg.manage_url, wait_until="domcontentloaded", timeout=120000)
                        page.wait_for_timeout(5000)
                        for link in _collect_links(page):
                            val = cfg.post_url_validator(link)
                            if val:
                                post_url = val
                                confirmed = True
                                break
                    except Exception:
                        pass

                if not confirmed:
                    return {"success": False, "error": "publish_not_confirmed", "platform": cfg.slug}

                return {
                    "success": True,
                    "platform": cfg.slug,
                    "publish_id": post_url or f"{cfg.slug}-{int(time.time())}",
                    "post_url": post_url,
                    "upload_selector": upload_sel,
                    "title_selector": title_sel,
                    "publish_selector": pub_sel,
                }
            finally:
                browser.close()
    except Exception as exc:
        return {"success": False, "error": str(exc)[:400], "platform": cfg.slug}
