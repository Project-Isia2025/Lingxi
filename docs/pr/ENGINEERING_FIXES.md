# 工程审查修复 — PR 拆分指南

本机未检测到 Git，请按下列分支顺序在本地创建 PR。

---

## PR #1 — P0：Celery 部署 + 数据源澄清

**分支：** `fix/p0-celery-datasource`

**文件：**
- `docker-compose.yml` — Celery Worker/Beat 默认启动；Postgres 移入 `infra` profile；注明 SQLite 为主库
- `infra/worker_health.py` — 新增 Celery worker 在线探测
- `infra/readiness.py` — Celery 模式下 readiness 检查 worker
- `services/workers/runtime.py` — Dashboard 不再误报 Celery 运行中
- `docs/ops.md` — 补充 SQLite 主库说明

**标题：** `fix: align Celery worker deployment with default WORKER_BACKEND=celery`

---

## PR #2 — P1：生产安全加固

**分支：** `fix/p1-security-hardening`

**文件：**
- `api/auth_policy.py` — 生产环境 `/docs`、`/metrics` 需 READ 鉴权
- `api/auth.py` — 生产禁用 query 传 API Key
- `config/settings.py` — 生产强制 CORS 白名单；新增相关 ENV
- `services/rpa_ingest.py` — 生产 RPA webhook 必须配置 secret
- `config/local.env.example`

**标题：** `fix: harden production auth, CORS, and RPA webhook`

---

## PR #3 — P1：SQLite 并发与可靠性

**分支：** `fix/p1-sqlite-wal`

**文件：**
- `core/db.py` — WAL + busy_timeout

**标题：** `fix: enable SQLite WAL and busy_timeout for multi-process access`

---

## PR #4 — P2：运维与清理调度

**分支：** `fix/p2-ops-cleanup`

**文件：**
- `infra/celery_schedule.py` — 独立 `task_cleanup_tick`
- `infra/celery_tasks.py`
- `services/workers/alert_cleanup_scheduler.py` — 解耦 task purge
- `config/settings.py` — `TASK_CLEANUP_ENABLED`

**标题：** `fix: independent task cleanup schedule and decouple from ROI alert cleanup`

---

## 本地命令示例

```powershell
cd "D:\Lingxi Engine"
git checkout -b fix/p0-celery-datasource
git add docker-compose.yml infra/worker_health.py infra/readiness.py services/workers/runtime.py docs/ops.md
git commit -m "fix: align Celery deployment with default worker backend"
git push -u origin fix/p0-celery-datasource
gh pr create --title "fix: Celery deployment + SQLite primary DB docs" --body "See docs/pr/ENGINEERING_FIXES.md PR #1"
```

依次重复 PR #2–#4。

---

## 测试

```powershell
python -m pytest tests/test_api_auth.py tests/test_api_auth_policy.py tests/test_celery_workers.py tests/test_task_cleanup.py tests/test_engineering_gaps.py -q
```
