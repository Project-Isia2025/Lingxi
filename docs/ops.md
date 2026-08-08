# 灵犀引擎 · 运维 Runbook

面向运营与工程师的日常部署、监控、排障指南。

## 1. 服务地址

| 组件 | 默认地址 | 说明 |
|------|----------|------|
| API | http://127.0.0.1:9200 | 主服务 |
| Dashboard | http://127.0.0.1:9200/dashboard | 运营控制台 |
| API 文档 | http://127.0.0.1:9200/docs | Swagger |
| 存活探针 | GET /api/health | 进程存活（K8s liveness） |
| 就绪探针 | GET /api/health/ready | SQLite + Redis（K8s readiness） |
| 深度探测 | GET /api/infra/health | Postgres/Redis/Qdrant/MinIO 全量 |
| Prometheus | http://127.0.0.1:9090 | 指标采集 |
| Grafana | http://127.0.0.1:3000 | 可视化（admin / 见 GRAFANA_PASSWORD） |

## 2. 快速启动

### 本机

```powershell
cd "D:\Lingxi Engine"
pip install -r requirements.txt
copy config\local.env.example config\local.env
python api_server.py
```

或双击 `启动灵犀引擎.bat`。

### Docker Compose（含监控 + Celery）

```powershell
docker compose up -d matrix-api celery-worker celery-beat redis prometheus grafana
```

Postgres 为可选：`docker compose --profile infra up -d postgres`

Grafana 预置 Dashboard：**灵犀引擎 · API 运维**（请求速率、P95 延迟、基础设施、Worker 状态）。

## 3. 健康检查说明

| 端点 | 用途 | 失败含义 |
|------|------|----------|
| `/api/health` | 浅检查，仅进程 | 服务崩溃 |
| `/api/health/ready` | SQLite 必检；Celery 模式 Redis + Worker 在线 | 不可接收流量 |
| `/api/infra/health` | Phase 0 全栈探测 | 某外围组件不可用 |

**K8s 建议：**

- `livenessProbe` → `/api/health`
- `readinessProbe` → `/api/health/ready`

## 4. 关键环境变量

| 变量 | 生产建议 | 说明 |
|------|----------|------|
| `ENVIRONMENT` | production | 启用生产密钥校验 |
| `PRIMARY_DB` | sqlite | **业务主库**为 `data/matrix_agent.db`；Postgres 仅可选（记忆/Campaign） |
| `WORKER_BACKEND` | celery | 需同时运行 `celery-worker` + `celery-beat`（Compose 默认已包含） |
| `API_AUTH_ENABLED` | 1 | API 鉴权 |
| `API_AUTH_KEY` | ≥16 位随机 | Bearer / X-API-Key（read/write） |
| `API_AUTH_ADMIN_KEY` | 可选独立密钥 | admin 路由（编排/发布/投流部署等） |
| `REVIEW_TOKEN_SECRET` | 强随机 | 审核链接签名 |
| `RPA_WEBHOOK_SECRET` | 强随机 | 影刀回调 |
| `WORKER_LEADER_LOCK_ENABLED` | 1 | 多副本防重复调度 |
| `REDIS_HOST` | redis | Leader 选举依赖 |
| `CORS_ORIGINS` | 白名单域名 | 禁止 `*` |

完整列表见 `config/local.env.example`。

### 4.1 API 鉴权分级

策略定义：`api/auth_policy.py`（40+ 条显式规则 + 兜底）。

| 等级 | 中间件 | 典型路由 |
|------|--------|----------|
| public | 放行 | `/api/health`、`/api/auth/login`（生产下 `/docs`、`/metrics` 需 READ） |
| webhook | 放行（端点验 secret） | `/api/rpa/webhook/*` |
| review | 放行（端点验 token） | `/api/review/{id}/approve` |
| dashboard | 放行 HTML | `/dashboard/*` |
| read | 需 API Key | `GET /api/**/status` |
| write | 需 API Key | `POST /api/**/scan`、`/trigger` |
| admin | 需 Admin Key* | `POST /api/orchestrator/run`、`/api/publish/run` |

\* 未配置 `API_AUTH_ADMIN_KEY` 时 admin 路由接受标准 Key。

调试：`GET /api/auth/policy?method=POST&path=/api/publish/run`

## 5. 后台 Worker

| Worker | 环境开关 | Leader Lock 名称 |
|--------|----------|------------------|
| 发布队列 | `PUBLISH_QUEUE_ENABLED=1` | publish-queue |
| 投流轮询 | `AD_POLL_ENABLED=1` | ad-report-poller |
| 感知调度 | `PERCEPTION_SCHEDULE_ENABLED=1` | perception-scheduler |
| ROI 报表 | `ROI_REPORT_SCHEDULE_ENABLED=1` | roi-report-scheduler |
| 告警清理 | `ROI_ALERT_CLEANUP_ENABLED=1` | alert-cleanup-scheduler |
| 发布后监控 | `POST_PUBLISH_MONITOR_ENABLED=1` | post-publish-monitor |

**多副本部署：** 必须开启 Redis + Leader Lock，否则每个 Pod 都会跑一遍定时任务。

**状态查看：** http://127.0.0.1:9200/dashboard/runtime

## 6. 编排路径

- **生产：** `POST /api/orchestrator/run`（五层 + Replan）
- **实验：** `POST /api/orchestrator/langgraph/run`（需 `LANGGRAPH_ORCHESTRATOR_ENABLED=1`）
- **说明：** `GET /api/orchestrator/routing`

## 7. 常见故障

### 7.1 `/api/health/ready` 返回 503

1. 检查 `data/matrix_agent.db` 是否可写
2. 若 `WORKER_LEADER_LOCK_ENABLED=1`，确认 Redis 可达
3. 本机无 Redis 时可临时设 `WORKER_LEADER_LOCK_ENABLED=0`（仅单实例）

### 7.2 发布队列不消费

1. `PUBLISH_QUEUE_ENABLED=1` 是否开启
2. 访问 `/api/publish/queue/status`
3. 查看日志中 `publish queue worker failed`
4. 多副本时确认只有一个 leader（Redis key `matrix:leader:publish-queue`）

### 7.3 影刀 Webhook 401/403

1. 确认 `RPA_WEBHOOK_SECRET` 与影刀配置一致
2. Header：`X-RPA-Webhook-Token` 或 Query `?token=`

### 7.4 Grafana 无数据

1. Prometheus target 应为 `matrix-api:9200`（见 `deploy/prometheus.yml`）
2. 访问 http://127.0.0.1:9200/metrics 应有 `commerce_agent_requests_total`
3. 确认 Grafana Datasource 指向 `http://prometheus:9090`

## 8. 备份

| 数据 | 路径 | 频率建议 |
|------|------|----------|
| SQLite 主库 | `data/matrix_agent.db` | 每日 |
| 配置文件 | `config/local.env` | 变更时 |
| 品牌/账号 JSON | `data/*.json` | 每日 |
| Playwright 登录态 | `data/state/*.json` | 变更时 |

## 9. 升级流程

1. 拉取新版本代码
2. `pip install -r requirements.txt`
3. 对比 `config/local.env.example` 新增变量
4. 运行 `python -m pytest -q` 或 CI 等价命令
5. 重启 `api_server.py` 或滚动更新 K8s Deployment
6. 验证 `/api/health/ready` 与核心 Dashboard

## 10. 监控指标

| 指标 | 含义 |
|------|------|
| `commerce_agent_requests_total` | HTTP 请求计数 |
| `commerce_agent_request_duration_seconds` | 请求延迟直方图 |
| `commerce_agent_infra_health` | SQLite/Redis 等健康 |
| `commerce_agent_worker_running` | Worker 是否在跑 |

## 11. 相关文档

- [README.md](../README.md) — 功能与 API 概览
- [docs/yingdao_setup.md](./yingdao_setup.md) — 影刀 RPA 对接
- [deploy/aliyun-fc/README.md](../deploy/aliyun-fc/README.md) — 阿里云 FC 部署

## 12. 代码结构（Phase 4）

```
core/db.py              # SQLite 连接 + schema_meta
core/migrate.py         # Alembic 封装（ensure_migrated / stamp / status）
core/migrations/        # Alembic 迁移脚本
core/storage/           # 领域模块 kb / metrics / review / publish / ad / monitors
services/workers/       # 后台 Worker 实现（旧路径 shim 仍可用）
```

## 13. 数据库迁移（Alembic）

| 命令 | 说明 |
|------|------|
| `python scripts/migrate.py status` | 当前 revision / schema 版本 |
| `python scripts/migrate.py upgrade` | 升级至 head |
| `python scripts/migrate.py stamp <rev>` | 仅标记版本（不执行 SQL） |

环境变量：

| 变量 | 默认 | 说明 |
|------|------|------|
| `DB_MIGRATE_ENABLED` | `1` | `0` 时使用 legacy `BASELINE_DDL` 初始化 |

启动流程（`api_server.py` lifespan）会调用 `init_storage()` → `ensure_migrated()`。

遗留 SQLite（已有业务表、无 `alembic_version`）首次启动会自动 stamp `001_baseline` 再执行后续增量迁移。

当前 head：`002_metrics_run_index`（`schema_meta.version = 2`，新增 `idx_content_metrics_run` 索引）。

## 14. 后台 Worker（Celery）

| 组件 | 命令 / 容器 | 职责 |
|------|-------------|------|
| Celery Worker | `python scripts/celery_worker.py` / `celery-worker` | 执行业务 tick 任务 |
| Celery Beat | `python scripts/celery_beat.py` / `celery-beat` | 按 ENV 间隔定时投递 |
| API | `api_server.py` | 不再启动 daemon 线程（`WORKER_BACKEND=celery`） |

任务名前缀：`commerce_agent.tasks.*`（发布队列、投流轮询、ROI 报表、告警清理、感知调度、发布后监控）。

Legacy 回退：`WORKER_BACKEND=thread` + `WORKER_LEADER_LOCK_ENABLED=1`（多副本 API 需 Redis 选主）。

手动触发示例：`POST /api/publish/worker/trigger`（Celery 模式下投递 `publish_queue_tick`）。
