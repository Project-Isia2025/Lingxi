"""Playwright 工具。"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator


def playwright_installed() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


@contextmanager
def playwright_sync_context() -> Iterator[Any]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        yield p
