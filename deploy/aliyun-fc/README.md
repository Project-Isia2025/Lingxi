# 阿里云函数计算（FC 3.0）部署 — Campaign API

将 `api/routes.py`（端口 8000 Campaign API）以 **Serverless HTTP 触发器** 方式部署，实现按需计费、弹性扩容。

## 前置条件

1. 阿里云账号 + 已开通函数计算 FC 3.0
2. 安装 [Serverless Devs CLI](https://www.serverless-devs.com/)：`npm i -g @serverless-devs/s`
3. 配置密钥：`s config add`（AccessKey / Secret）

## 目录说明

| 文件 | 说明 |
|------|------|
| `handler.py` | FC 入口，HTTP 事件 → FastAPI ASGI |
| `s.yaml` | Serverless Devs 部署模板 |
| `Dockerfile.fc` | 可选：自定义容器镜像（含 ffmpeg） |

## 方式一：代码包部署（推荐联调）

```bash
# 在项目根目录
cd deploy/aliyun-fc
s deploy -y
```

部署完成后 CLI 会输出 HTTP 触发 URL，例如：

```
https://xxxx.cn-hangzhou.fc.aliyuncs.com/health
```

验证：

```bash
curl -sS "https://YOUR-FC-URL/health"
curl -sS "https://YOUR-FC-URL/api/campaigns"
```

## 方式二：自定义容器（生产 / 需 ffmpeg）

```bash
# 构建镜像（在项目根目录）
docker build -f deploy/aliyun-fc/Dockerfile.fc -t lingxi-campaign-fc:latest .

# 推送至阿里云 ACR 后在 FC 控制台创建「自定义容器」函数
# 启动命令: uvicorn api.routes:app --host 0.0.0.0 --port 9000
# 监听端口: 9000
```

## 环境变量

在 FC 控制台或 `s.yaml` 的 `environmentVariables` 中配置：

```env
DATABASE_URL=postgresql+asyncpg://...
REDIS_HOST=...
LLM_API_BASE=...
LLM_API_KEY=...
VIDEO_OUTPUT_DIR=/tmp/videos
```

完整变量参考 `config/local.env.example`。

## 本地验证 handler

```bash
python scripts/validate_aliyun_fc.py
```

## 与主服务关系

| 服务 | 入口 | 端口 | 部署建议 |
|------|------|------|----------|
| 运营主 API | `api_server.py` | 9200 | Docker Compose / Windows 服务 |
| Campaign API | `api/routes.py` | 8000 | **本 FC 模板** 或 `deploy/Dockerfile` |

主服务 `api_server.py` 已通过 `api/endpoints/campaign.py` 挂载 Campaign 路由；FC 侧独立部署 Campaign 模块即可实现「AI 任务按需跑、非 24h 满负荷」。

## 影刀 Webhook 回调地址

影刀任务完成后 POST 到主服务（9200）：

```
POST http://YOUR-HOST:9200/api/rpa/webhook/yingdao?token=YOUR_RPA_WEBHOOK_SECRET
Content-Type: application/json

{
  "platform": "douyin",
  "keyword": "护肤",
  "items": [
    {"title": "爆款标题", "url": "https://...", "likes": 12000, "comments": 430}
  ]
}
```

数据会写入 `data/state/rpa_ingest.json`，`perceive_market` 优先使用 RPA 回写数据。
