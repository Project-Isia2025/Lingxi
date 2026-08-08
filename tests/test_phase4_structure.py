"""Phase 4: storage 拆分 + workers 目录测试。"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bootstrap

bootstrap.ensure_paths()


def test_storage_domain_modules_importable():
    from core.storage import kb_search, metrics_record, enqueue_review, enqueue_publish, save_ad_campaign

    assert callable(kb_search)
    assert callable(metrics_record)
    assert callable(enqueue_review)
    assert callable(enqueue_publish)
    assert callable(save_ad_campaign)


def test_schema_version_table():
    from core.db import init_storage, schema_version

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "schema.db"
        import core.db as db_mod
        import core.storage as storage_mod

        with __import__("unittest").mock.patch.object(db_mod, "DB_PATH", db):
            storage_mod.DB_PATH = db
            init_storage()
            assert schema_version() == "2"


def test_workers_package_and_shims():
    from services.workers import start_background_worker
    from services.publish_worker import start_background_worker as shim_start

    assert start_background_worker is shim_start


def test_deploy_readiness_manifest_check():
    from services.deploy_status import validate_helm_chart, validate_k8s_yaml

    k8s = validate_k8s_yaml()
    helm = validate_helm_chart()
    assert k8s.get("ok") is True
    assert helm.get("ok") is True
