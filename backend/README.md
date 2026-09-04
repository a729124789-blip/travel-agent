# 智能旅行助手 · 后端

基于 **FastAPI + LangGraph + RAG** 的智能旅行规划助手后端。融合了「差旅出行助手（CLI）」的 Agent 多智能体系统与「旅行多Agent助手」的 FastAPI 外壳，支持**自然语言对话式**与**表单直通式**两种行程规划入口，并提供 SSE 流式输出。

## 技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| Web 框架 | FastAPI + Uvicorn | HTTP 入口，自带 `/docs` 交互式 API 文档 |
| Agent 编排 | LangGraph | 8 节点有向图，`Send` 动态并行调度（P1 并行 → join → P2 规划） |
| LLM 接入 | langchain-openai (ChatOpenAI) | 腾讯云 tokenhub，默认 `deepseek-v4-flash-0731` |
| 嵌入模型 | sentence-transformers | 本地 `bge-small-zh-v1.5`（512 维） |
| 向量库 | Milvus（Docker） | collection `business_travel_knowledge`（COSINE） |
| 实时搜索 | DDGS | 信息查询节点（非天气类问题走网络搜索） |
| 记忆存储 | JSON 文件 | `data/memory/{user_id}.json`（长期记忆，可升级数据库） |
| 数据校验 | Pydantic v2 + pydantic-settings | 请求模型 + 配置管理 |
| 日志 | Loguru | 结构化日志输出 |
| 稳定性 | 自研 utils | 熔断器、重试、JSON 解析容错（`app/utils/`） |

## 核心架构

```
用户输入 (自然语言 / 表单字段)
        │
        ▼
┌─────────────── LangGraph 图 ───────────────┐
│  START → load_memory → intent              │
│       │   （intent 解析出 agent_schedule）  │
│       ▼   Send 动态并行 fan-out            │
│   ├─ event_collection  事项收集             │
│   ├─ preference        偏好提取/追加        │
│   ├─ info_query        实时信息查询(搜索)   │
│   ├─ rag               RAG 知识库问答       │
│   └─ memory_query      长期记忆问答         │
│       │                                    │
│       ▼                                    │
│   join →（有目的地&规划意图？）             │
│   ├─ yes → itinerary_planning → aggregate  │
│   └─ no  → aggregate（普通问答汇总）        │
│       → save_memory → END                  │
└────────────────────────────────────────────┘
        │
        ▼
final_response（前端 Markdown 渲染 / SSE 打字机）
```

- **load_memory**：注入长期记忆（偏好、行程历史、对话摘要、短期上下文）
- **intent**：多意图识别 + 关键实体提取 + 查询改写 + 生成调度计划
- **event_collection**：提取出发地/目的地/日期/天数/交通等结构化信息（交通方式按距离自动推断）
- **itinerary_planning**：基于 event_info + 用户偏好生成每日行程
- **aggregate**：纯 Python 拼装最终回复（不调 LLM，保证快速稳定）
- **save_memory**：偏好写回 + 行程历史保存 + 默认出发地(last_origin)闭环 + 对话记录

### 两条入口路径

1. **自然语言对话** `/api/chat/message`：完整 8 节点图，自动识别意图路由
2. **表单直通** `/api/chat/form-plan`：跳过 intent 二次识别，直接用前端结构化字段构造 event_info 强制走规划链路（避免拼接句被误判）

## 项目结构

```
backend/
├── app/
│   ├── main.py                 # FastAPI 应用入口（CORS / 路由注册 / health）
│   ├── config.py               # Pydantic Settings 统一配置（.env）
│   ├── graph.py                # LangGraph 图组装（节点注册/边/条件路由/记忆闭环）
│   ├── state.py                # TravelState 状态定义
│   ├── api/routes/
│   │   ├── chat.py             # 【开发测试】8 个节点测试端点（/docs 一键调用，含默认用例）
│   │   └── chat_api.py         # 【正式】面向前端对话 API（intent/plan/message/form-plan/history/preferences + SSE 流式）
│   ├── nodes/                  # 8 个图节点
│   │   ├── intent.py           # 意图识别
│   │   ├── event_collection.py # 事项收集
│   │   ├── preference.py       # 偏好提取
│   │   ├── info_query.py       # 信息查询
│   │   ├── rag.py              # RAG 知识库
│   │   ├── memory_query.py     # 记忆查询
│   │   ├── itinerary_planning.py # 行程规划
│   │   └── aggregate.py        # 聚合输出
│   ├── services/
│   │   ├── llm_service.py      # LLM 调用封装（按任务类型分模型 + 熔断）
│   │   ├── rag_service.py      # RAG 检索服务（Milvus + bge）
│   │   └── search_service.py   # DDGS 网络搜索
│   ├── memory/
│   │   ├── memory_manager.py   # 记忆管理器（长期+短期）
│   │   ├── long_term.py        # 长期记忆（JSON 文件持久化）
│   │   └── short_term.py       # 短期记忆（会话上下文）
│   └── utils/
│       ├── circuit_breaker.py  # 熔断器
│       ├── llm_resilience.py   # LLM 重试/降级
│       └── json_parser.py      # LLM 输出 JSON 解析容错
├── data/
│   ├── memory/                 # 长期记忆（{user_id}.json）
│   ├── documents/              # RAG 知识库源文档（8 个商旅文档）
│   └── models/bge-small-zh-v1.5/ # 本地嵌入模型（366MB）
├── scripts/
│   └── init_knowledge_base.py  # RAG 知识库初始化脚本
├── .env                        # 环境变量（含 LLM_API_KEY）
├── .env.example                # 环境变量模板
└── requirements.txt
```

## 快速开始

### 环境要求

- Python >= 3.11
- Docker（Milvus 向量库）
- 本地嵌入模型 `bge-small-zh-v1.5` 位于 `data/models/` 下（首次运行前需准备）

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填写：

```env
# ===== LLM（腾讯云 tokenhub）=====
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://tokenhub.tencentmaas.com/v1
# 模型在 app/config.py 的 llm_models 中按任务类型配置（当前统一 deepseek-v4-flash-0731）
```

### 3. 启动 Milvus（Docker）

```bash
# 若尚未启动 Milvus 容器
docker run -d --name milvus -p 19530:19530 -p 9091:9091 milvusdb/milvus:latest
```

### 4. 初始化 RAG 知识库（首次）

```bash
cd backend
python scripts/init_knowledge_base.py
```

该脚本会从 `data/documents/` 向量化商旅文档写入 Milvus，并测试检索。

### 5. 启动后端

```bash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

> 注意：**需在 `backend/` 目录下启动**（依赖相对路径 `data/` 与 `.env`）。建议 `PYTHONPATH` 包含 backend 根目录。

启动后：
- 健康检查：http://127.0.0.1:8000/health
- 交互式 API 文档：http://127.0.0.1:8000/docs

## API 一览

### 正式接口（面向前端，`/api` 前缀）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat/intent` | 意图识别（表单预填充用） |
| POST | `/api/chat/plan` | 行程规划（完整 graph） |
| POST | `/api/chat/message` | 通用对话（完整 graph） |
| POST | `/api/chat/form-plan` | 表单直通行程规划 |
| POST | `/api/chat/message/stream` | **SSE 流式**通用对话（进度事件 + 打字机） |
| POST | `/api/chat/form-plan/stream` | **SSE 流式**表单直通行程规划 |
| GET | `/api/chat/history` | 历史会话（对话 + 行程 + 偏好 + 统计） |
| GET | `/api/preferences` | 读取偏好 |
| POST | `/api/preferences` | 保存偏好（replace/append） |
| GET | `/api/chat/llm-status` | LLM 熔断器状态 |

### 开发测试端点（`/docs` 一键调用，含默认用例）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/test/event-collection` | 事项收集（默认：南京→杭州 3 日游） |
| POST | `/api/test/intent` | 意图识别（默认：3月去杭州+住汉庭） |
| POST | `/api/test/preference` | 偏好提取（默认：我还喜欢如家） |
| POST | `/api/test/memory-query` | 记忆查询（默认：我去过哪些地方？） |
| POST | `/api/test/info-query` | 信息查询（默认：杭州天气怎么样？） |
| POST | `/api/test/rag` | RAG 知识库问答（默认：出差住宿标准是多少？） |
| POST | `/api/test/itinerary` | 行程规划（默认：南京→杭州 3 日游） |
| POST | `/api/test/aggregate` | 聚合输出（默认：完整行程格式化） |

### SSE 流式事件格式

`/api/chat/message/stream` 返回 `text/event-stream`，事件为 `data: {json}\n\n`：

```json
{"type": "progress", "node": "rag", "message": "正在检索商旅知识库..."}
{"type": "delta", "content": "根据知识库..."}   // 每 4 字符一块，打字机效果
{"type": "done"}
```

## 记忆系统

长期记忆以 JSON 文件持久化于 `data/memory/{user_id}.json`，包含：

- **preferences**：用户偏好（last_origin 默认出发地 / hotel_brands / food_preference 等）
- **chat_history**：完整对话记录（role / content / timestamp / session_id）
- **trip_history**：历史行程足迹（行程 ID / 起止 / 目的地 / 摘要）
- **statistics**：统计信息（总行程数 / 总消息数 / 常去目的地）

记忆闭环：`load_memory` 注入 → `save_memory` 写回。**last_origin 机制**：行程确认后自动把本次出发地存为默认出发地，下次无需重复填写。

## 设计要点

- **核心与补充分离**：Agent 编排逻辑不依赖具体数据源，搜索/RAG/记忆均为可插拔节点
- **交通方式自动推断**：同城(<100km)→公共交通；100~800km→高铁；>800km→飞机；用户指定优先
- **表单直通**：前端确认表单后走 `form-plan` 直达规划，避免拼接自然语言被 intent 二次误判
- **LLM 按任务分模型**：intent/planning/rag 可配不同模型与 temperature（当前统一，预留优化空间）
- **多用户隔离**：按 `user_id` 隔离记忆与图状态（thread_id）
