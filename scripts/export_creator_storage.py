"""导出创作者中心登录态（抖音/小红书/视频号）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()

TARGETS = {
    "douyin": {
        "url": "https://creator.douyin.com/",
        "out": bootstrap.project_root() / "data" / "state" / "douyin_creator_storage.json",
        "env": "DOUYIN_PUBLISH_STORAGE_STATE",
    },
    "xhs": {
        "url": "https://creator.xiaohongshu.com/",
        "out": bootstrap.project_root() / "data" / "state" / "xhs_creator_storage.json",
        "env": "XHS_PUBLISH_STORAGE_STATE",
    },
    "shipinhao": {
        "url": "https://channels.weixin.qq.com/",
        "out": bootstrap.project_root() / "data" / "state" / "shipinhao_creator_storage.json",
        "env": "SHIPINHAO_PUBLISH_STORAGE_STATE",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="导出创作者中心登录态")
    parser.add_argument("platform", choices=list(TARGETS.keys()), help="douyin | xhs | shipinhao")
    args = parser.parse_args()
    cfg = TARGETS[args.platform]
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("pip install playwright && python -m playwright install chromium")
        return 1

    out: Path = cfg["out"]
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"打开 {cfg['url']} ，登录创作者中心后按 Enter 保存…")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chrome")
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
        page = context.new_page()
        page.goto(cfg["url"], wait_until="domcontentloaded")
        input("登录完成后按 Enter… ")
        context.storage_state(path=str(out))
        browser.close()
    print(f"已保存: {out}")
    print(f"请在 config/local.env 设置: {cfg['env']}={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
