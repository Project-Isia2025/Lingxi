"""工程师落地版 — 技术栈对照（LangChain + 低代码 + 平台 API）。"""

from __future__ import annotations



from typing import Any



STACK_LAYERS: list[dict[str, Any]] = [

    {

        "id": "orchestration",

        "layer": "Agent 编排框架",

        "tech_plan": "LangGraph（LangChain 升级版）",

        "tech_project": "LangGraph + 五层 OrchestratorAgent",

        "status": "implemented",

        "status_label": "已落地",

        "role": "管理 5 个 Agent 之间的状态流转、条件分支与循环；比 AutoGen 更可控",

        "paths": [

            "orchestrator/graph.py",

            "orchestrator/orchestrator_agent.py",

            "orchestrator/nodes.py",

            "api/endpoints/workflow.py",

        ],

        "env": [],

        "notes": "运营入口走 OrchestratorAgent（感知→决策→执行+Replan）；LangGraph 用于 Campaign/ROI 循环场景",

    },

    {

        "id": "llm",

        "layer": "大模型底座",

        "tech_plan": "Claude 3.7 / GPT-4o / 通义千问",

        "tech_project": "OpenAI 兼容 API（LangChain ChatOpenAI）",

        "status": "implemented",

        "status_label": "已落地",

        "role": "负责策略推理、脚本生成、数据解读；建议多模型轮换防封",

        "paths": ["agents/content/script_generator.py", "services/llm_router.py", "config/local.env.example"],

        "env": ["LLM_API_BASE", "LLM_API_KEY", "LLM_MODEL", "LLM_MODELS", "LLM_ROTATION_ENABLED"],

        "notes": "services/llm_router.py 支持 LLM_MODELS 多模型轮换；GET /api/engineering/llm 查看状态",

    },

    {

        "id": "vector",

        "layer": "向量数据库",

        "tech_plan": "Milvus / Pinecone",

        "tech_project": "Qdrant（docker-compose）+ 内存兜底",

        "status": "implemented",

        "status_label": "已落地（等价替换）",

        "role": "存储历史爆款素材、脚本、违禁词，为 Agent 提供 RAG 检索",

        "paths": [

            "memory/vector_store.py",

            "memory/knowledge_base.py",

            "memory/banned_words.py",

            "docker-compose.yml",

        ],

        "env": ["QDRANT_HOST", "QDRANT_PORT", "OPENAI_API_KEY"],

        "notes": "Qdrant 与 Milvus/Pinecone 职责等价；无向量库时自动降级 memory 模式",

    },

    {

        "id": "rpa",

        "layer": "自动化 RPA",

        "tech_plan": "影刀 RPA / 八爪鱼",

        "tech_project": "Playwright 爬虫 + 影刀 Webhook 感知回写",

        "status": "implemented",

        "status_label": "已落地",

        "role": "抓取抖音/视频号后台数据；官方 API 拿不到的数据用浏览器自动化或低代码 RPA 补位",

        "paths": [

            "agents/perception/scraper.py",

            "services/perception.py",

            "services/rpa_ingest.py",

            "api/endpoints/rpa.py",

            "data/rpa_field_mapping.example.json",

            "data/yingdao_webhook.example.json",

            "scripts/acceptance_rpa_webhook.py",

            "docs/yingdao_setup.md",

            "api/endpoints/rpa_setup.html",

            "docker-compose.yml (matrix-playwright)",

        ],

        "env": [

            "DOUYIN_STORAGE_STATE",

            "XHS_STORAGE_STATE",

            "RPA_WEBHOOK_SECRET",

            "RPA_INGEST_ENABLED",

        ],

        "notes": "Playwright + 影刀 Webhook；运营向导 /dashboard/rpa；文档 docs/yingdao_setup.md",

    },

    {

        "id": "content_api",

        "layer": "内容生成 API",

        "tech_plan": "HeyGen API / 剪映开放平台",

        "tech_project": "HeyGen + CapCut Provider + ffmpeg 混剪路由",

        "status": "implemented",

        "status_label": "已落地",

        "role": "替代人工剪辑师，自动生成推广视频",

        "paths": [

            "services/video_providers/heygen.py",

            "services/video_providers/capcut.py",

            "services/video_providers/router.py",

            "services/strategy.py (plan_video_cost)",

            "agents/content/",

        ],

        "env": [

            "VIDEO_PROVIDER",

            "HEYGEN_API_KEY",

            "CAPCUT_API_KEY",

            "CAPCUT_TEMPLATE_ID",

            "VIDEO_MIX_ENABLED",

        ],

        "notes": "VIDEO_PROVIDER=heygen|capcut|volc|kling|template；未配置 Key 时自动 mock 占位成片",

    },

    {

        "id": "approval",

        "layer": "消息与审批",

        "tech_plan": "飞书 Open API",

        "tech_project": "飞书 Webhook 卡片 + 工作流决策 API",

        "status": "implemented",

        "status_label": "已落地",

        "role": "AI 推任务给人「点头确认」，结果回写工作流继续执行",

        "paths": [

            "services/feishu_review.py",

            "services/review_queue.py",

            "services/workflow_decisions.py",

            "api/endpoints/review.py",

            "api/endpoints/workflow.py",

        ],

        "env": ["REVIEW_FEISHU_WEBHOOK_URL", "REVIEW_BASE_URL", "REVIEW_QUEUE_ENABLED"],

        "notes": "Dashboard /api/workflow/decisions 与飞书卡片双通道；人类仅点头确认与应急兜底",

    },

    {

        "id": "deploy",

        "layer": "部署方式",

        "tech_plan": "Docker + 阿里云 FC",

        "tech_project": "Docker Compose + 阿里云 FC Serverless 模板",

        "status": "implemented",

        "status_label": "已落地",

        "role": "弹性按需扩容，AI 任务非 24 小时满负荷，节省成本",

        "paths": [

            "docker-compose.yml",

            "deploy/Dockerfile",

            "deploy/aliyun-fc/s.yaml",

            "deploy/aliyun-fc/handler.py",

            "deploy/aliyun-fc/README.md",

            "deploy/aliyun-fc/production.md",

        ],

        "env": ["API_PORT", "DATABASE_URL", "REDIS_HOST"],

        "notes": "Docker + FC 3.0；生产 VPC/RDS 见 deploy/aliyun-fc/production.md",

    },

]



PHILOSOPHY = {

    "stack": "LangChain + 低代码工具 + 平台 API",

    "pattern": "AI 感知·决策·执行，人类点头确认与应急兜底",

    "engines": [

        {"name": "OrchestratorAgent", "use": "主工作流（运营入口）"},

        {"name": "LangGraph", "use": "Campaign ROI 循环 / Phase 6 验收"},

    ],

}





def build_engineering_stack() -> dict[str, Any]:

    implemented = sum(1 for x in STACK_LAYERS if x["status"] == "implemented")

    partial = sum(1 for x in STACK_LAYERS if x["status"] == "partial")

    return {

        "ok": True,

        "title": "技术实现方案（工程师落地版）",

        "subtitle": PHILOSOPHY["stack"],

        "philosophy": PHILOSOPHY,

        "summary": f"7 层技术栈：{implemented} 层已落地，{partial} 层部分落地",

        "layers": STACK_LAYERS,

        "quick_start": [

            "copy config\\local.env.example config\\local.env",

            "docker compose up -d postgres redis qdrant minio",

            "python api_server.py  或  启动灵犀引擎.bat",

            "配置 LLM_API_* / REVIEW_FEISHU_WEBHOOK_URL / HEYGEN_API_KEY / RPA_WEBHOOK_SECRET",

        ],

        "next_steps": [

            "复制 data/rpa_field_mapping.example.json 并按影刀列名定制",

            "配置 LLM_MODELS 多模型轮换（DeepSeek/通义/GPT）",

            "FC 生产 VPC + RDS 联调（deploy/aliyun-fc/production.md）",

        ],

    }

