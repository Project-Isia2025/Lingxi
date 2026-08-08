# 阿里云 FC 生产环境 — VPC + RDS 联调指南

面向 Campaign API（`api/routes.py`）的生产部署，与本地 Docker Compose 栈对齐。

## 架构建议

```
                    ┌─────────────────┐
  影刀 / 运营端 ──► │  SLB / API GW   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        FC: campaign   FC: worker      ECS: 主 API
        (api/routes)   (可选 Celery)   (api_server 9200)
              │              │
              └────── VPC 内网 ──────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    RDS PostgreSQL   Redis        Qdrant/向量
```

| 组件 | 推荐规格 | 说明 |
|------|----------|------|
| FC 函数 | 1 GB / 120s | HTTP 触发，按需计费 |
| RDS | PostgreSQL 14+ | 与 `DATABASE_URL` 一致 |
| Redis | 云 Redis 标准版 | Celery / 缓存 |
| VPC | 同地域内网互通 | FC 绑定 VPC 访问 RDS |

## 1. 准备 RDS

```sql
CREATE DATABASE lingxi;
CREATE USER lingxi WITH PASSWORD 'your-strong-password';
GRANT ALL PRIVILEGES ON DATABASE lingxi TO lingxi;
```

连接串（FC 环境变量）：

```env
DATABASE_URL=postgresql+asyncpg://lingxi:your-strong-password@rm-xxxxx.pg.rds.aliyuncs.com:5432/lingxi
```

## 2. FC 绑定 VPC

在函数配置中：

1. **网络**：选择与 RDS 相同的 VPC、交换机
2. **安全组**：放行 FC 网段 → RDS 5432、Redis 6379
3. **环境变量**：从 `config/local.env.example` 复制生产值

```env
REDIS_HOST=r-xxxxx.redis.rds.aliyuncs.com
REDIS_PORT=6379
QDRANT_HOST=内网 Qdrant 或 ECS IP
LLM_API_BASE=https://your-gateway/v1
LLM_API_KEY=sk-...
LLM_MODELS=deepseek-chat,qwen-max,gpt-4o
LLM_ROTATION_ENABLED=1
RPA_WEBHOOK_SECRET=prod-secret
```

## 3. 部署命令

```bash
# 安装 Serverless Devs
npm i -g @serverless-devs/s
s config add

# 修改 deploy/aliyun-fc/s.yaml 中 region / serviceName
cd deploy/aliyun-fc
s deploy -y

# 本地验证 handler
python scripts/validate_aliyun_fc.py
python scripts/acceptance_rpa_webhook.py
```

## 4. 自定义容器（含 ffmpeg）

适合需要视频混剪的 Campaign 节点：

```bash
docker build -f deploy/aliyun-fc/Dockerfile.fc -t registry.cn-hangzhou.aliyuncs.com/YOUR_NS/lingxi-campaign:latest .
docker push registry.cn-hangzhou.aliyuncs.com/YOUR_NS/lingxi-campaign:latest
```

FC 控制台创建「自定义容器」函数，端口 **9000**，启动命令已写在 Dockerfile。

## 5. 与主服务分工

| 流量 | 部署位置 | 入口 |
|------|----------|------|
| 运营 Dashboard / 工作流 | ECS 或 Windows 服务 | `api_server.py:9200` |
| Campaign ROI 循环 | FC 按需 | `api/routes.py` |
| 影刀 RPA 回调 | 主服务 9200 | `POST /api/rpa/webhook/yingdao` |

影刀任务应回调 **主服务 9200**（感知数据写入本地/共享存储）；FC 仅承担 Campaign 弹性 API。

## 6. 验收清单

- [ ] `curl https://FC_URL/health` 返回 `status: healthy`
- [ ] `curl https://FC_URL/api/campaigns` 可访问
- [ ] RDS 连接无公网暴露（仅 VPC 内）
- [ ] `python scripts/acceptance_rpa_webhook.py` PASS
- [ ] 影刀 HTTP 步骤 POST 示例 JSON 后，`GET /api/rpa/records` 有记录

## 7. 常见问题

**FC 冷启动慢**：配置最小实例数 ≥ 1，或使用预留实例。

**RDS 连接超时**：确认 FC 已绑定 VPC，且 RDS 白名单包含 FC 安全组。

**视频生成失败**：FC 代码包无 ffmpeg，请改用 `Dockerfile.fc` 自定义容器。
