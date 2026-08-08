"""metrics run_id index

Revision ID: 002_metrics_run_index
Revises: 001_baseline
Create Date: 2026-07-30
"""
from __future__ import annotations

from alembic import op

revision = "002_metrics_run_index"
down_revision = "001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_content_metrics_run ON content_metrics(run_id, event_type)"
    )
    op.execute("UPDATE schema_meta SET value='2' WHERE key='version'")
    op.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('alembic_revision', '002_metrics_run_index')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_content_metrics_run")
    op.execute("UPDATE schema_meta SET value='1' WHERE key='version'")
    op.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('alembic_revision', '001_baseline')"
    )
