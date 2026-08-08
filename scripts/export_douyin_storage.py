"""导出抖音 PC 登录态（storage_state）供爬虫使用。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()

OUT = bootstrap.project_root() / "data" / "state" / "douyin_pc_storage.json"


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("请先安装: pip install playwright && python -m playwright install chromium")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    print("将打开浏览器，请手动登录抖音 PC 版，登录成功后回到终端按 Enter…")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chrome")
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
        page = context.new_page()
        page.goto("https://www.douyin.com/", wait_until="domcontentloaded")
        input("登录完成后按 Enter 保存登录态… ")
        context.storage_state(path=str(OUT))
        browser.close()
    print(f"已保存: {OUT}")
    print("可在 config/local.env 中设置: DOUYIN_STORAGE_STATE=" + str(OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
