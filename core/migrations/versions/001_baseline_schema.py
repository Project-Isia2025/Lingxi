"""baseline schema

Revision ID: 001_baseline
Revises:
Create Date: 2026-07-30
"""
from __future__ import annotations

from alembic import op

from core.schema_sql import BASELINE_DDL, ddl_statements

revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in ddl_statements(BASELINE_DDL):
        op.execute(stmt)
    op.execute("INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('version', '1')")
    op.execute(
        "INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('alembic_revision', '001_baseline')"
    )


def downgrade() -> None:
    tables = [
        "post_publish_monitors",
        "review_queue",
        "alert_sent_log",
        "publish_queue",
        "publish_accounts",
        "ad_campaigns",
        "episodic_memory",
        "script_history",
        "publish_log",
        "publish_state",
        "execution_jobs",
        "content_metrics",
        "forbidden_words",
        "kb_items",
        "schema_meta",
    ]
    for table in tables:
        op.execute(f"DROP TABLE IF EXISTS {table}")
