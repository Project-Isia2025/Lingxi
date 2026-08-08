# 影刀 RPA 对接灵犀引擎 — 完整配置指南

> 运营可视化向导：http://127.0.0.1:9200/dashboard/rpa  
> API 说明：http://127.0.0.1:9200/api/rpa/guide

## 一、整体流程

```
影刀抓取抖音/小红书表格
        ↓
流程末尾「HTTP 请求」POST JSON
        ↓
灵犀 /api/rpa/webhook/yingdao
        ↓
perceive_market 优先使用 RPA 数据
        ↓
AI 工作流 感知→决策→执行
```

## 二、灵犀引擎侧（5 分钟）

### 1. 配置 Webhook 密钥（推荐）

编辑 `config/local.env`：

```env
RPA_WEBHOOK_SECRET=请换成随机字符串
RPA_INGEST_ENABLED=1
```

重启服务：`python api_server.py` 或双击 `启动灵犀引擎.bat`。

### 2. 复制字段映射

```bash
python scripts/setup_rpa_mapping.py
```

或打开 http://127.0.0.1:9200/dashboard/rpa 点击「一键复制字段映射文件」。

若影刀表格列名是**中文**（标题、链接、点赞数），默认映射即可。  
若列名不同，编辑 `data/rpa_field_mapping.json` 中 `field_aliases`。

### 3. 验证

```bash
python scripts/acceptance_rpa_webhook.py
```

或在向导页点击「发送测试数据」。

---

## 三、影刀侧 — HTTP 请求逐步填表

在 RPA 流程**最后一步**（抓取循环结束后）插入 **「HTTP 请求」** 指令：

| 字段 | 填写内容 |
|------|----------|
| **请求方式** | `POST` |
| **URL** | `http://你的服务器IP:9200/api/rpa/webhook/yingdao?token=你的RPA_WEBHOOK_SECRET` |
| **Headers** | `Content-Type: application/json` |
| **Headers（可选）** | `X-RPA-Webhook-Token: 你的RPA_WEBHOOK_SECRET` |
| **Body 类型** | JSON / 原始文本 |
| **Body** | 见下方模板 |

### Body JSON 模板

```json
{
  "task_id": "{{流程运行ID}}",
  "platform": "douyin",
  "keyword": "{{搜索关键词变量}}",
  "items": [
    {
      "标题": "{{当前行.标题}}",
      "链接": "{{当前行.链接}}",
      "点赞数": {{当前行.点赞数}},
      "评论数": {{当前行.评论数}},
      "播放量": {{当前行.播放量}}
    }
  ]
}
```

> 说明：`{{...}}` 替换为影刀实际变量语法（如 `[表格]`、`{变量名}`，以你使用的影刀版本为准）。

### 两种常见写法

**A. 循环内逐行 POST（简单）**  
在「ForEach 表格行」循环内，每行 POST 一条 `items` 数组（仅 1 个元素）。

**B. 循环外批量 POST（推荐）**  
循环结束后，用影刀「组装 JSON / 列表转 JSON」把整张表合成 `items` 数组，一次性 POST。

---

## 四、字段对照表

| 灵犀标准字段 | 影刀常见列名 | 用途 |
|-------------|-------------|------|
| title | 标题、视频标题、name | 竞品标题 |
| url | 链接、作品链接、share_url | 视频链接 |
| likes | 点赞数、digg_count | 互动量 |
| comments | 评论数 | 互动量 |
| views | 播放量、play_count | 流量 |
| keyword | 搜索词（Body 顶层） | 与工作流目标匹配 |
| platform | douyin / xiaohongshu | 平台 |

完整映射见 `data/rpa_field_mapping.example.json`。

---

## 五、与工作流联动

1. 影刀定时跑抓取 → POST 回写竞品
2. 运营在 http://127.0.0.1:9200/dashboard 填写推广目标（如「护肤」）
3. AI 感知阶段优先读 RPA 缓存（72 小时内、关键词匹配）
4. 无需人工导入 Excel

查看回写记录：

- 页面：http://127.0.0.1:9200/dashboard/rpa
- API：`GET /api/rpa/records`

---

## 六、故障排查

| 现象 | 处理 |
|------|------|
| 401 / invalid_webhook_token | 检查 URL 中 `token=` 与 `local.env` 中 `RPA_WEBHOOK_SECRET` 一致 |
| no_items | Body 需含 `items` 数组，且每行至少有「标题」映射到 title |
| 工作流没用 RPA 数据 | 检查 keyword 是否与工作流目标相关；记录是否超过 `RPA_INGEST_MAX_AGE_HOURS` |
| 影刀连不上 | 服务器防火墙放行 9200；本机测试用 `127.0.0.1`，影刀在别的电脑用局域网 IP |

---

## 七、相关文件

| 路径 | 说明 |
|------|------|
| `api/endpoints/rpa_setup.html` | 运营向导页 |
| `services/rpa_ingest.py` | 回写与映射逻辑 |
| `data/yingdao_webhook.example.json` | Body 示例 |
| `scripts/acceptance_rpa_webhook.py` | 自动化验收 |
