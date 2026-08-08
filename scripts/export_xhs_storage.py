"""导出小红书 PC 搜索登录态（Playwright storage_state）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()

OUT = bootstrap.project_root() / "data" / "state" / "xhs_pc_storage.json"


def main() -> None:
    from playwright.sync_api import sync_playwright

    from services.xhs import common as xc

    OUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"请在打开的浏览器中登录小红书，完成后回到终端按 Enter…")
    print(f"登录态将保存到: {OUT}")

    with sync_playwright() as p:
        browser = xc.launch_browser(p, headless=False)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        xc.apply_stealth(context)
        page = context.new_page()
        page.goto("https://www.xiaohongshu.com/", wait_until="domcontentloaded", timeout=xc.nav_timeout_ms())
        input("登录完成后按 Enter 保存…")
        context.storage_state(path=str(OUT))
        browser.close()
    print(f"已保存: {OUT}")


if __name__ == "__main__":
    main()
