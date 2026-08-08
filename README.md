# 五层 AI 智能体矩阵 · Lingxi Engine

项目目录：`D:\Lingxi Engine`（原 `D:\五层AI智能体（Agent）矩阵`）

与 `D:\AI口播获客智能体` **无任何代码依赖**，是单独的多 Agent 工作流系统。

## 架构

```
👑 总控大脑 → 📊数据感知 → 📦记忆库 → 🧠策略 → ✍️内容 → 🚀执行
                              ↓
                    Plan → Observe → Replan（可选）
```

**Agent 顺序**：数据感知 → 记忆库 → 策略 → 内容 → 执行

## 快速启动

```powershell
cd "D:\Lingxi Engine"
pip install -r requirements.txt
python api_server.py
```

- 服务：`http://127.0.0.1:9200`（默认端口，避免与 AI口播智能体 9100 冲突）
- API 文档：`http://127.0.0.1:9200/docs`
- 调价规则 UI：`http://127.0.0.1:9200/dashboard/ad-bid`
- 运维中心：`http://127.0.0.1:9200/dashboard/runtime`

## CLI

```powershell
python cli.py --keyword "护肤" --platform xhs --sync
python cli.py --keyword "护肤" --auto-execute --sync

# 矩阵发布 + Replan
python cli.py --keyword "护肤" \
  --video-path "D:/videos/demo.mp4" \
  --auto-matrix \
  --publish-platforms "douyin,xiaohongshu" \
  --enable-replan --max-iterations 3 \
  --sync
```

| 参数 | 说明 |
|------|------|
| `--video-path` | 本地成片路径 |
| `--auto-publish` | 立即发布到创作者中心 |
| `--auto-matrix` | 联合 ROI 策略矩阵入队 |
| `--publish-platforms` | 发布平台（逗号分隔） |
| `--enable-replan` | 启用 Replan 循环 |

## 配置

复制 `config/local.env.example` 为 `config/local.env`，按需填写 LLM、爬虫登录态、发布登录态、投流、ASR 等。

未配置 LLM 时，内容 Agent 自动使用模板兜底。

### API 鉴权（按路由分级）

在 `config/local.env` 中配置：

```env
ENVIRONMENT=production
API_AUTH_ENABLED=1
API_AUTH_KEY=至少16位随机字符串
API_AUTH_ADMIN_KEY=可选，独立管理密钥（高危路由专用）
CORS_ORIGINS=https://你的域名
```

**鉴权等级**（`api/auth_policy.py`）：

| 等级 | 说明 | 示例 |
|------|------|------|
| `public` | 无需 Key | `/api/health`、`/metrics`、`/api/auth/login` |
| `webhook` | 端点内校验 Webhook Secret | `/api/rpa/webhook/*`、`/api/review/callback` |
| `review` | 端点内校验 review token | `/api/review/{id}/approve` |
| `dashboard` | HTML 页面公开，子 API 需 Key | `/dashboard/*` |
| `read` | 只读 API，需标准 Key | `GET /api/orchestrator/status` |
| `write` | 写入/触发，需标准 Key | `POST /api/perception/scan` |
| `admin` | 高危操作，需 Admin Key（未配置则回退标准 Key） | `POST /api/orchestrator/run` |

- 请求头：`X-API-Key` 或 `Authorization: Bearer`
- Dashboard 首次 401 时提示输入 Key 并写入 Cookie
- 查询路由等级：`GET /api/auth/policy?method=POST&path=/api/publish/run`
- 登录：`POST /api/auth/login` `{ "api_key": "..." }`

开发环境默认 `API_AUTH_ENABLED=0`，行为与之前一致。

### Phase 2 架构（配置 / 多副本 / 编排）

```env
# pydantic-settings 集中配置（config/settings.py）
WORKER_LEADER_LOCK_ENABLED=1    # 多副本 API 仅一个实例跑后台任务
REDIS_HOST=localhost

# LangGraph 为实验路径，生产请用 POST /api/orchestrator/run
LANGGRAPH_ORCHESTRATOR_ENABLED=0
```

- 编排说明：`GET /api/orchestrator/routing`
- 存储层：`core/db.py`（Schema）+ `core/storage/`（业务 API，兼容 `from core.storage import ...`）

### Phase 3 可观测性

```powershell
docker compose up -d matrix-api prometheus grafana
```

- 就绪探针：`GET /api/health/ready`（SQLite + Redis）
- 全量探测：`GET /api/infra/health`
- Grafana：http://127.0.0.1:3000（预置 Dashboard「灵犀引擎 · API 运维」）
- 运维 Runbook：[docs/ops.md](docs/ops.md)

### Phase 4 结构整理

- `core/storage/` 按领域拆分：`kb` · `metrics` · `review` · `publish` · `ad` · `monitors`
- `services/workers/` 集中后台任务（旧 `services/publish_worker` 等路径仍兼容）

### 数据库迁移（Alembic + schema_meta）

默认 `DB_MIGRATE_ENABLED=1`：启动时自动升级至最新 revision，并在 `schema_meta` 同步数字版本。

```powershell
# 查看迁移状态
python scripts/migrate.py status

# 手动升级至 head
python scripts/migrate.py upgrade

# 新建空 revision（手工编写 upgrade/downgrade）
python scripts/migrate.py revision -m "add foo column"
```

- 迁移目录：`core/migrations/versions/`
- 健康检查：`GET /api/health` 返回 `db_schema_version` / `db_alembic_revision`
- 遗留库（有表无 `alembic_version`）会自动 `stamp 001_baseline` 再 `upgrade head`
- 关闭 Alembic 回退 legacy DDL：`DB_MIGRATE_ENABLED=0`

### 后台 Worker（Celery，替代线程 + Leader Lock）

默认 `WORKER_BACKEND=celery`：API 进程**不再**启动 in-process 线程；由 **Celery Beat** 定时投递、**Celery Worker** 消费执行。

```powershell
# 终端 1：API
python api_server.py

# 终端 2：Worker
python scripts/celery_worker.py

# 终端 3：Beat 调度
python scripts/celery_beat.py
```

Docker Compose（含 beat）：

```powershell
docker compose --profile worker up -d matrix-api celery-worker celery-beat redis
```

| 变量 | 默认 | 说明 |
|------|------|------|
| `WORKER_BACKEND` | `celery` | `thread` 回退 legacy 线程 + Redis Leader Lock |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | 消息队列 |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/2` | 任务结果 |

各 worker 开关仍用原有 ENV（如 `PUBLISH_QUEUE_ENABLED`、`ROI_ALERT_CLEANUP_ENABLED` 等）；Beat 只为已启用的任务生成调度。

## 工作流 API

```json
POST /api/orchestrator/run
{
  "keyword": "护肤",
  "platform": "xhs",
  "enable_replan": true,
  "auto_execute": true,
  "auto_matrix_publish": true,
  "video_path": "D:/videos/demo.mp4",
  "sync": true
}
```

`auto_matrix_publish=true` 会在工作流结束时按联合 ROI 策略自动矩阵入队（需 `video_path` + 口播文案）。  
**无需**同时设置 `auto_publish`：仅矩阵入队时不会立即发布，也不会创建 execution job。

| 参数 | auto_publish | auto_matrix_publish | 行为 |
|------|:------------:|:-------------------:|------|
| 仅矩阵 | false | true | 按 ROI 策略入队，不立即发布 |
| 立即发布 | true | false | 单账号创作者中心发布 |
| 两者都开 | true | true | 立即发布 + 矩阵入队 |

## 各模块能力

| Agent | 功能 |
|-------|------|
| 总控 | 顺序调度、冲突仲裁、ROI 评分、Plan→Observe→Replan |
| 数据感知 | 抖音/小红书 Playwright 爬虫、笔记深度抓取、OCR/ASR、RSS 热点 |
| 记忆库 | SQLite RAG、品牌配置、违禁词、ASR/OCR 自动入库 |
| 策略 | 选品、定价、投流计划 |
| 内容 | LLM 改写、OCR/ASR 注入、去重、TTS A/B、ffmpeg 混剪计划 |
| 执行 | 自动发布、多账号队列、投流部署与报表闭环 |

## 爬虫

### 抖音

```powershell
pip install playwright
python -m playwright install chromium
python scripts/export_douyin_storage.py
```

```env
DOUYIN_CRAWLER_ENABLED=1
DOUYIN_STORAGE_STATE=data/state/douyin_pc_storage.json
```

- `GET /api/douyin/search?keyword=护肤`

### 小红书

```env
XHS_CRAWLER_ENABLED=1
XHS_STORAGE_STATE=data/state/xhs_pc_storage.json
XHS_ENRICH_DETAIL=1
XHS_OCR_ENABLED=1
XHS_ASR_ENABLED=1
```

- `GET /api/xhs/search?keyword=护肤`
- `GET /api/xhs/note?url=...`
- `POST /api/xhs/note/ocr`

## ASR 视频转写

配置 Whisper 兼容 API（OpenAI / 自建）：

```env
ASR_ENABLED=1
ASR_API_BASE=https://api.openai.com/v1
ASR_API_KEY=sk-...
ASR_MODEL=whisper-1
ASR_MEMORY_ENABLED=1
```

- `GET /api/asr/status`
- `POST /api/asr/transcribe` — 支持 `save_to_memory` 写入热点库

转写结果会自动注入内容 Agent prompt，并在笔记抓取/感知阶段写入 `hotspot` 知识库。

## 自动发布

### 导出创作者登录态

```powershell
python scripts/export_creator_storage.py douyin
python scripts/export_creator_storage.py xhs
python scripts/export_creator_storage.py shipinhao
```

### 单条发布

```powershell
curl -X POST http://127.0.0.1:9200/api/publish/run ^
  -H "Content-Type: application/json" ^
  -d "{\"platform\":\"douyin\",\"video_path\":\"D:/videos/demo.mp4\",\"script\":\"口播文案\"}"
```

### 多账号矩阵调度

账号配置：`data/publish_accounts.json`（或通过 `GET /api/publish/accounts` 查看）

```json
POST /api/publish/matrix
{
  "video_path": "D:/videos/demo.mp4",
  "script": "口播文案",
  "platforms": ["douyin", "xiaohongshu"]
}
```

执行队列：

```json
POST /api/publish/queue/run
```

后台 Worker（类似投流轮询）：

```env
PUBLISH_QUEUE_ENABLED=1
PUBLISH_QUEUE_INTERVAL_SEC=300
PUBLISH_QUEUE_BATCH_SIZE=5
```

- `GET /api/publish/queue/status`
- `POST /api/publish/queue/start`
- `POST /api/publish/queue/trigger?sync=true`

## 投流与自动调价

```env
AD_POLL_ENABLED=1
AD_POLL_INTERVAL_SEC=3600
AD_AUTO_BID_ENABLED=1
AD_BID_RULES_PATH=data/ad_bid_rules.json
```

- `POST /api/ad/deploy`
- `POST /api/ad/report/sync?run_id=...`
- `POST /api/ad/bid/evaluate?run_id=...&apply=true`
- `GET/POST /api/ad/bid/rules`
- 可视化配置：`/dashboard/ad-bid`
- 感知 Feed（ASR/OCR/发布）：`/dashboard/perception`

## 发布 ROI 回写与队列重试

发布成功后会自动：
- 写入 `publish_ok` / `publish_roi` 指标
- 回写热点库并提升 ROI 分
- 记录 episodic 记忆

```env
PUBLISH_ROI_ENABLED=1
PUBLISH_QUEUE_RETRY_ENABLED=1
PUBLISH_QUEUE_MAX_RETRIES=3
PUBLISH_QUEUE_RETRY_DELAY_SEC=600
```

失败任务（非登录态/配额类可重试）会自动延迟重新入队。

- `GET /api/dashboard/perception-feed` — ASR/OCR/发布 Feed JSON
- `WS /ws/dashboard/feed` — 实时推送（发布/ASR/OCR/联合 ROI 更新）
- `GET /api/roi/combined/{run_id}` — 联合 ROI 查询（`persist=true` 写入库）
- `GET /api/roi/metrics/{run_id}` — run 指标明细

### 发布队列优先级

```json
POST /api/publish/schedule
{"platform":"douyin","video_path":"...","script":"...","priority":10,"run_id":"run-001"}
```

`priority` 越大越优先；带 `run_id` 的任务会根据联合 ROI 动态调整（`PUBLISH_DYNAMIC_PRIORITY=1`）。

```json
POST /api/publish/queue/refresh-priority
```

### 联合 ROI 驱动投流调价

联合 ROI 计算完成后，可自动调整投流日预算：

```env
COMBINED_ROI_BID_ENABLED=1
COMBINED_ROI_BID_SCALE=0.72
COMBINED_ROI_BID_CUT=0.38
```

- `POST /api/ad/bid/combined?run_id=...&apply=true`

### ROI 图表 Dashboard

- `http://127.0.0.1:9200/dashboard/analytics` — 发布/投流/联合 ROI 趋势图
- `GET /api/dashboard/metrics-chart?days=14`
- `WS /ws/dashboard/analytics` — 图表实时推送
- `GET /api/roi/export/csv?days=30` — ROI 报表 CSV 下载

### 联合 ROI 矩阵发布策略

根据联合 ROI 自动决定平台数、账号数与优先级：

| 联合 ROI | 策略 |
|---------|------|
| ≥ 0.75  | 抖音+小红书，每平台 2 账号 |
| ≥ 0.55  | 抖音+小红书，每平台 1 账号 |
| ≥ 0.35  | 仅抖音 |
| < 0.30  | 跳过矩阵分发 |

```json
POST /api/publish/matrix/auto
{"run_id":"run-001","video_path":"data/out/video.mp4","script":"口播文案"}
```

- `GET /api/roi/matrix/strategy/{run_id}` — 仅查看策略不发布

### P1 成片增强 / 发布后监控

```env
BGM_ENABLED=1
VISUAL_DEDUP_ENABLED=1
VIDEO_GEN_ENABLED=1
VOLC_API_KEY=your-key
VOLC_API_URL=https://your-volc-video-api/submit
POST_PUBLISH_MONITOR_ENABLED=1
COMPLETION_RATE_MIN=0.30
TAKEDOWN_ENABLED=0
```

- 混剪自动加 BGM（`mix_plan.bgm`）+ 视觉去重（滤镜/变速/可选 PIP）
- `services/video_providers/router.py` — volc/kling/avatar API 或 mock 占位成片
- `POST /api/monitor/post-publish/poll` — 轮询到期监控
- 低完播/CTR → 自动下架记录 + 触发 content replan

### P0 感知 / 库存策略 / 飞书审核

```env
PERCEPTION_SCHEDULE_ENABLED=1
PERCEPTION_INTERVAL_SEC=1800
PERCEPTION_MIN_LIKE_RATE=0.05
REVIEW_QUEUE_ENABLED=1
REVIEW_FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
REVIEW_BASE_URL=http://127.0.0.1:9200
```

- `POST /api/perception/scan` — 立即扫描热榜+竞品（点赞率>5%）并入库黄金话术/BGM
- `GET /api/douyin/hotlist` — 抖音热榜
- `GET /api/inventory` — 店铺库存（`data/inventory.json`）
- 策略输出 `daily_directive`：库存驱动 + 3×15s 切片指令
- `GET /api/review/status` — 审核队列
- `POST /api/review/callback` — 飞书卡片回调（URL 验证 + 确认/打回）
- `GET /api/review/{id}/approve?token=...` — 链接式确认（兼容）
- `GET /api/douyin/video/{video_id}` — 竞品详情页播放量/点赞率
- `GET /dashboard/review?review_id=...` — 打回表单（原因写入 sop 知识库）

### ROI 定时报表与告警

```env
ROI_REPORT_SCHEDULE_ENABLED=1
ROI_REPORT_INTERVAL_SEC=86400
ROI_REPORT_EMAIL_TO=ops@example.com
SMTP_HOST=smtp.example.com
ROI_ALERT_WEBHOOK_URL=https://your-webhook-url
```

- `POST /api/roi/report/send?days=30` — 立即生成并发送/保存报表
- `GET /api/roi/report/status` — 定时任务状态
- `POST /api/roi/alert/test` — 测试 Webhook 告警（`force=true` 跳过去重）

Webhook 自动识别飞书 / 企业微信 URL，或通过 `ROI_ALERT_WEBHOOK_PROVIDER=feishu|wecom` 指定格式。  
同一 run + 告警类型在 `ROI_ALERT_DEDUP_SEC` 内不重复推送。  
过期去重记录默认保留 7 天，可通过定时任务或 API 清理：

```env
ROI_ALERT_CLEANUP_ENABLED=1
ROI_ALERT_CLEANUP_INTERVAL_SEC=86400
ROI_ALERT_CLEANUP_RETENTION_SEC=604800
```

- `GET /api/roi/alert/status` — 告警与清理任务状态
- `POST /api/roi/alert/cleanup?retention_sec=604800` — 立即清理过期记录

## 数据目录

| 路径 | 说明 |
|------|------|
| `data/matrix_agent.db` | 运行记录、知识库、投流、发布队列 |
| `data/brand.json` | 品牌/CTA/行业 |
| `data/ad_bid_rules.json` | 调价规则（UI 可编辑） |
| `data/publish_accounts.json` | 多账号发布配置 |
| `data/state/*.json` | Playwright 登录态 |

## Windows 服务

```powershell
.\scripts\windows\install_service.ps1
Start-ScheduledTask -TaskName "MatrixAgent-API"
```

## 测试

```powershell
python -m pytest tests/ -q
```

当前覆盖：工作流、爬虫、发布、投流、OCR/ASR、调价、多账号队列等。
