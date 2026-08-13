"""verify_local_setup 脚本测试。"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


def test_verify_local_setup_runs():
    from scripts.verify_local_setup import run_checks

    with patch.dict(
        "os.environ",
        {"WORKER_BACKEND": "thread", "WORKER_LEADER_LOCK_ENABLED": "0", "LLM_API_KEY": ""},
        clear=False,
    ):
        report = run_checks()
    assert "checks" in report
    assert any(c["name"] == "sqlite" for c in report["checks"])
