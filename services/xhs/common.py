"""小红书爬虫共用工具。"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import bootstrap

_STEALTH_JS = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"


def project_root() -> Path:
    return bootstrap.project_root()


def xhs_enabled() -> bool:
    return os.environ.get("XHS_CRAWLER_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def parse_count_text(raw: str | None) -> int | None:
    s = (raw or "").strip().replace(",", "").replace(" ", "")
    if not s:
        return None
    s = s.replace("+", "")
    mult = 1.0
    if "亿" in s:
        mult = 100_000_000.0
        s = s.replace("亿", "")
    elif "万" in s or s.lower().endswith("w"):
        mult = 10_000.0
        s = re.sub(r"[万wW]", "", s)
    m = re.search(r"([\d.]+)", s)
    if not m:
        return None
    try:
        return int(float(m.group(1)) * mult)
    except (TypeError, ValueError):
        return None


def _first_file(*candidates: str) -> str:
    for c in candidates:
        p = Path(c).expanduser()
        if c and p.is_file():
            return str(p.resolve())
    return ""


def resolve_storage_state() -> str:
    env = (os.environ.get("XHS_STORAGE_STATE") or os.environ.get("XHS_CRAWLER_STORAGE_STATE") or "").strip()
    if env:
        return _first_file(env)
    for name in ("xhs_pc_storage.json", "xhs_creator_storage.json"):
        default = project_root() / "data" / "state" / name
        if default.is_file():
            return str(default.resolve())
    return ""


def resolve_cookie_file() -> str:
    env = (os.environ.get("XHS_COOKIE_FILE") or "").strip()
    if env:
        return _first_file(env)
    default = project_root() / "data" / "state" / "xhs_cookies.txt"
    return str(default.resolve()) if default.is_file() else ""


def build_search_url(keyword: str) -> str:
    kw = quote((keyword or "").strip())
    return f"https://www.xiaohongshu.com/search_result?keyword={kw}&source=web_search_result_notes"


def playwright_headless() -> bool:
    return os.environ.get("XHS_PLAYWRIGHT_HEADLESS", "1").strip().lower() not in ("0", "false", "no", "off")


def captcha_wait_sec() -> int:
    try:
        return max(15, int(os.environ.get("XHS_CAPTCHA_WAIT_SEC", "120")))
    except ValueError:
        return 120


def collect_wait_sec() -> int:
    try:
        return max(20, int(os.environ.get("XHS_COLLECT_WAIT_SEC", "90")))
    except ValueError:
        return 90


def nav_timeout_ms() -> int:
    try:
        return int(os.environ.get("XHS_NAV_TIMEOUT_MS", "60000"))
    except ValueError:
        return 60_000


def debug_dir() -> Path:
    d = project_root() / "data" / "xhs_debug"
    d.mkdir(parents=True, exist_ok=True)
    return d


def playwright_installed() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def netscape_to_playwright_cookies(text: str, domain: str = ".xiaohongshu.com") -> list[dict[str, Any]]:
    cookies: list[dict[str, Any]] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        name, value = parts[5], parts[6]
        cookies.append({"name": name, "value": value, "domain": domain, "path": "/"})
    return cookies


def browser_context_kwargs(*, storage_state: str = "", cookie_file: str = "") -> dict[str, Any]:
    kw: dict[str, Any] = {
        "viewport": {"width": 1440, "height": 900},
        "locale": "zh-CN",
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
    }
    if storage_state:
        kw["storage_state"] = storage_state
    elif cookie_file:
        try:
            raw = Path(cookie_file).read_text(encoding="utf-8")
            cookies = netscape_to_playwright_cookies(raw)
            if cookies:
                kw["storage_state"] = {"cookies": cookies, "origins": []}
        except OSError:
            pass
    return kw


def launch_browser(p, *, headless: bool | None = None):
    use_headless = playwright_headless() if headless is None else headless
    launch_kw: dict[str, Any] = {"headless": use_headless}
    channel = (os.environ.get("XHS_PLAYWRIGHT_CHANNEL") or "").strip()
    if channel:
        launch_kw["channel"] = channel
        return p.chromium.launch(**launch_kw)
    try:
        return p.chromium.launch(**launch_kw)
    except Exception:
        for ch in ("chrome", "msedge"):
            try:
                kw = dict(launch_kw)
                kw["channel"] = ch
                return p.chromium.launch(**kw)
            except Exception:
                continue
        raise RuntimeError("无法启动浏览器。请安装 playwright chromium")


def apply_stealth(context) -> None:
    context.add_init_script(_STEALTH_JS)


def page_has_captcha(page) -> bool:
    try:
        if "验证" in (page.title() or ""):
            return True
        low = page.content().lower()
        return any(x in low for x in ("captcha", "verify", "滑块", "security"))
    except Exception:
        return False


def wait_for_content(page, *, max_sec: int, selector: str) -> bool:
    deadline = time.time() + max(5, int(max_sec))
    while time.time() < deadline:
        if not page_has_captcha(page):
            try:
                n = int(page.evaluate(f"() => document.querySelectorAll({selector!r}).length") or 0)
                if n > 0:
                    return True
            except Exception:
                pass
        try:
            page.mouse.wheel(0, 1800)
        except Exception:
            pass
        page.wait_for_timeout(1500)
    return False
