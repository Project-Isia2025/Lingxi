"""SQLite baseline DDL — 供 Alembic 001 基线迁移引用。"""

BASELINE_DDL = """
CREATE TABLE IF NOT EXISTS kb_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    library TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    roi_score REAL NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    updated_ts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS forbidden_words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT NOT NULL UNIQUE,
    word_type TEXT NOT NULL DEFAULT 'forbidden',
    replace_word TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS content_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    metric_value REAL NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS execution_jobs (
    job_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT 'queued',
    payload_json TEXT NOT NULL,
    updated_ts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS publish_state (
    platform TEXT NOT NULL,
    account_id TEXT NOT NULL DEFAULT 'default',
    last_publish_ts INTEGER NOT NULL DEFAULT 0,
    last_day TEXT NOT NULL DEFAULT '',
    day_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (platform, account_id)
);
CREATE TABLE IF NOT EXISTS publish_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    video_path TEXT NOT NULL DEFAULT '',
    post_url TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS script_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL DEFAULT '',
    dedupe_hash TEXT NOT NULL DEFAULT '',
    script TEXT NOT NULL DEFAULT '',
    keyword TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_script_hash ON script_history(dedupe_hash);
CREATE TABLE IF NOT EXISTS episodic_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    agent TEXT NOT NULL DEFAULT '',
    observation TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ad_campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'douyin',
    keyword TEXT NOT NULL DEFAULT '',
    daily_budget REAL NOT NULL DEFAULT 0,
    dry_run INTEGER NOT NULL DEFAULT 0,
    last_report_json TEXT NOT NULL DEFAULT '{}',
    updated_ts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ad_run ON ad_campaigns(run_id);
CREATE TABLE IF NOT EXISTS publish_accounts (
    platform TEXT NOT NULL,
    account_id TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    storage_state TEXT NOT NULL DEFAULT '',
    daily_limit INTEGER NOT NULL DEFAULT 4,
    enabled INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (platform, account_id)
);
CREATE TABLE IF NOT EXISTS publish_queue (
    job_id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    account_id TEXT NOT NULL DEFAULT 'default',
    video_path TEXT NOT NULL DEFAULT '',
    script TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    scheduled_ts INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_ts INTEGER NOT NULL DEFAULT 0,
    updated_ts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_publish_queue_status ON publish_queue(status, scheduled_ts);
CREATE TABLE IF NOT EXISTS alert_sent_log (
    dedupe_key TEXT PRIMARY KEY,
    run_id TEXT NOT NULL DEFAULT '',
    alert_type TEXT NOT NULL DEFAULT '',
    sent_ts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alert_sent_ts ON alert_sent_log(sent_ts);
CREATE TABLE IF NOT EXISTS review_queue (
    review_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL DEFAULT '',
    video_path TEXT NOT NULL DEFAULT '',
    script TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending_review',
    reject_reason TEXT NOT NULL DEFAULT '',
    feishu_msg_id TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_ts INTEGER NOT NULL DEFAULT 0,
    updated_ts INTEGER NOT NULL DEFAULT 0,
    reviewed_ts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_review_status ON review_queue(status, created_ts);
CREATE TABLE IF NOT EXISTS post_publish_monitors (
    monitor_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    post_url TEXT NOT NULL DEFAULT '',
    job_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    due_ts INTEGER NOT NULL DEFAULT 0,
    completion_rate REAL,
    ctr REAL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_ts INTEGER NOT NULL DEFAULT 0,
    updated_ts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_post_monitor_due ON post_publish_monitors(status, due_ts);
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
"""

# revision_id -> numeric schema version in schema_meta.version
REVISION_VERSION_MAP: dict[str, str] = {
    "001_baseline": "1",
    "002_metrics_run_index": "2",
}


def ddl_statements(ddl: str) -> list[str]:
    """Split DDL script into individual statements for Alembic/SQLAlchemy."""
    return [stmt.strip() for stmt in ddl.split(";") if stmt.strip()]
