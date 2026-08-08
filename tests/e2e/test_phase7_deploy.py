"""Phase 7 部署与项目结构 E2E 测试。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


def test_phase7_file_structure():
    required = [
        "api/routes.py",
        "api/schemas.py",
        "deploy/Dockerfile",
        "tests/unit/",
        "tests/integration/",
        "tests/e2e/",
    ]
    for p in required:
        path = ROOT / p
        assert path.exists(), f"missing: {p}"


def test_dockerfile_content():
    dockerfile = (ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    assert "ffmpeg" in dockerfile
    assert "api.routes:app" in dockerfile
    assert "8000" in dockerfile


def test_routes_app_importable():
    from api.routes import app

    assert app.title == "Content Commerce Agent API"


def test_test_directories_have_files():
    unit = list((ROOT / "tests" / "unit").glob("test_*.py"))
    integration = list((ROOT / "tests" / "integration").glob("test_*.py"))
    e2e = list((ROOT / "tests" / "e2e").glob("test_*.py"))
    assert len(unit) >= 3
    assert len(integration) >= 2
    assert len(e2e) >= 1
