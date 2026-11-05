# OpenCGP

> Open Content Generation Platform · 以对话为中心、以作品为活文档的 AI 创作工作台

> 以对话为中心、以课程为活文档的独立 Web 工作台——AI 当作者兼助教，人在关键处拍板，产出成体系的图文知识课程。

本仓库为 **M0 / Sprint 0** 阶段脚手架，已按「Ports & Adapters（可插拔）」架构落地，保证后续无缝切换 PostgreSQL / pgvector / rustfs 等生产基础设施而不返工。

完整设计见 [`docs/course-studio-design.md`](docs/course-studio-design.md)。

---

## 目录结构

```
.
├── backend/                  # FastAPI 应用
│   ├── app/
│   │   ├── main.py           # FastAPI 入口 + /health
│   │   ├── config.py         # 配置加载器（.env / 环境变量，单一来源）
│   │   ├── container.py      # 极简依赖注入装配
│   │   ├── ports/            # 抽象接口（Protocol）
│   │   │   ├── database.py   #   Database
│   │   │   ├── storage.py    #   StorageBackend
│   │   │   ├── llm.py        #   LLMProvider
│   │   │   ├── vectorstore.py#   VectorStore
│   │   │   ├── course_repository.py      #   课程/讲/版本仓库
│   │   │   ├── conversation_repository.py#   对话线（thread/message）仓库
│   │   │   └── exporter.py   #   Exporter
│   │   └── adapters/         # 具体实现（builtin 默认）
│   │       ├── database/sqlite.py
│   │       ├── storage/local.py
│   │       ├── llm/openai_compat.py      # 占位
│   │       ├── vectorstore/simple.py     # 占位
│   │       └── exporter/builtin.py       # 占位
│   ├── requirements.txt
│   └── .env.example
├── frontend/                 # Next.js (React/TS) 应用
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx          # 占位首页
│   │   └── globals.css       # 最简 CSS（未引入 Tailwind）
│   ├── package.json
│   ├── next.config.js
│   └── tsconfig.json
├── docs/                     # 设计文档归档
│   └── course-studio-design.md
├── .env.example
├── docker-compose.yml        # 单机一键起（占位）
└── README.md
```

---

## 架构要点（Ports & Adapters）

一切基础设施与业务能力皆可插拔：

1. **抽象接口**：`backend/app/ports/*.py` 用 Python `Protocol` 定义端口。
2. **Adapter 实现**：`backend/app/adapters/*` 内置 `builtin`（单机）实现，生产可新增 `external` 实现。
3. **依赖注入**：业务代码只依赖端口，由 `container.py` 按配置选择 adapter。
4. **配置驱动**：统一前缀 `COURSE_STUDIO_`，切换 adapter 只改 `.env`。

| 模块 | M0 内置（默认） | 生产可切 |
|---|---|---|
| Database | SQLite | PostgreSQL / pgvector |
| StorageBackend | 本地文件 | S3 兼容 / rustfs / OSS |
| LLMProvider | OpenAI 兼容（占位） | DeepSeek / 豆包 / 通义 / vLLM |
| VectorStore | 关键词+朴素向量（占位） | pgvector / Qdrant / Milvus |
| Exporter | builtin（占位） | pandoc / weasyprint 渲染服务 |

---

## 快速启动（M0 阶段）

### 后端（FastAPI）

```bash
cd backend

# 1. 安装依赖（建议使用虚拟环境）
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. （可选）准备环境变量
cp .env.example .env

# 3. 启动
uvicorn app.main:app --reload --port 8000
```

验证：

```bash
# 语法编译检查
python -m compileall app

# 可导入检查
python -c "from app.main import app"

# 健康检查
curl http://localhost:8000/health
# 交互式 API 文档
open http://localhost:8000/docs
```

### 前端（Next.js）

```bash
cd frontend

# 1. 安装依赖
npm install

# 2. 启动开发服务器
npm run dev
```

浏览器打开 http://localhost:3000 查看占位首页。

---

## 配置说明

- 后端所有配置经 `backend/app/config.py` 读取，前缀 `COURSE_STUDIO_`，支持 `.env`（`.env` 不覆盖已存在的环境变量）。
- 完整配置项见 [`backend/.env.example`](backend/.env.example)。
- 前端跨域/API 地址后续用 `NEXT_PUBLIC_API_BASE_URL` 注入。

### Rerank 专用模型

`COURSE_STUDIO_RERANK_BACKEND` 支持下列预设，全部走专用 rerank 端点（不是 chat completions）。`none` 为默认；`llm` 复用聊天模型打分，仅在无专用 rerank 服务时兜底，效果与成本都不如专用模型。

| 预设 | 默认 URL | 默认 model | 协议 |
|---|---|---|---|
| `cohere` | `https://api.cohere.com/v1/rerank` | `rerank-v3.5` | Cohere |
| `jina` | `https://api.jina.ai/v1/rerank` | `jina-reranker-v2-base-multilingual` | Cohere |
| `siliconflow` | `https://api.siliconflow.cn/v1/rerank` | `BAAI/bge-reranker-v2-m3` | Cohere |
| `zhipu` | `https://open.bigmodel.cn/api/paas/v4/rerank` | `rerank` | Cohere |
| `tei` | `http://127.0.0.1:8080/rerank` | `BAAI/bge-reranker-v2-m3` | TEI |
| `generic` | 手动指定 | 手动指定 | Cohere 请求 / 兼容多种响应 |

鉴权统一为 `Authorization: Bearer $COURSE_STUDIO_RERANK_API_KEY`；显式设置的 `RERANK_BASE_URL` / `RERANK_MODEL` 覆盖预设默认值。

```bash
# Cohere（key: https://dashboard.cohere.com/api-keys）
COURSE_STUDIO_RERANK_BACKEND=cohere
COURSE_STUDIO_RERANK_API_KEY=...

# Jina（key: https://jina.ai/reranker/）
COURSE_STUDIO_RERANK_BACKEND=jina
COURSE_STUDIO_RERANK_API_KEY=...

# SiliconFlow（key: https://cloud.siliconflow.cn/account/ak）
COURSE_STUDIO_RERANK_BACKEND=siliconflow
COURSE_STUDIO_RERANK_API_KEY=...

# 智谱（key: https://open.bigmodel.cn/usercenter/apikeys）
COURSE_STUDIO_RERANK_BACKEND=zhipu
COURSE_STUDIO_RERANK_API_KEY=...

# TEI 自建（无需 key）
COURSE_STUDIO_RERANK_BACKEND=tei
COURSE_STUDIO_RERANK_BASE_URL=http://127.0.0.1:8080/rerank
COURSE_STUDIO_RERANK_BATCH=32
```

调优项：`RERANK_BATCH`（默认 100，Cohere 上限 100，TEI 默认 32）、`RERANK_CHARS`（单条文档字符截断，默认 2000，按字符非 token）、`RERANK_NORMALIZE=auto|sigmoid|minmax|none`（默认 auto）、`RERANK_RAW_SCORES`（TEI 返回 logits 时设 `true`，默认 false）、`RERANK_RETRIES=2`（仅重试 429/5xx/超时）。失败时检索自动回落到混合检索原序，不会中断请求。

---

## API 一览（M0）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查（各 adapter 探活） |
| POST | `/api/v1/kb/upload` | 上传知识库文档（pdf/docx/md/txt） |
| POST | `/api/v1/kb/search` | 检索知识库，返回带来源的引用 |
| DELETE | `/api/v1/kb/sources/{source_id}` | 删除知识源与其分块 |
| POST | `/api/v1/courses` | 创建课程 |
| GET | `/api/v1/courses` | 课程列表 |
| GET | `/api/v1/courses/{course_id}` | 课程详情（含讲次） |
| POST | `/api/v1/courses/{course_id}/lessons` | 创建讲次 |
| GET | `/api/v1/courses/{course_id}/lessons` | 讲次列表 |
| GET | `/api/v1/lessons/{lesson_id}` | 讲次详情（当前正文与版本号） |
| POST | `/api/v1/lessons/{lesson_id}/generate` | 单讲生成（`mode=strict` 带引用 / `loose` 大模型自由写作，落 vN） |
| GET | `/api/v1/lessons/{lesson_id}/versions` | 版本历史 |
| POST | `/api/v1/lessons/{lesson_id}/revert` | 回滚到指定版本（追加新版本） |
| POST | `/api/v1/lessons/{lesson_id}/ask` | 追问：基于正文 + 证据 + 对话线作答 |
| POST | `/api/v1/lessons/{lesson_id}/amend` | 局部修改（支持 `mode=strict/loose`）：按自然语言指令落新版本 |
| POST | `/api/v1/lessons/{lesson_id}/drilldown` | 沉淀：把某次追问回答追加进该讲 |
| GET | `/api/v1/lessons/{lesson_id}/thread` | 该讲对话线（消息 + 证据） |
| GET | `/api/v1/threads/{thread_id}` | 按对话线 ID 读取消息 |

追问 / 修改 / 沉淀都复用追加式版本机制：正文变更只新增 `lesson_versions`，指令原文写入版本 `note`，历史可 diff、可回滚。

### 生成模式（strict / loose）

`generate` 与 `amend` 都接受可选字段 `mode`，默认 `strict`：

| 模式 | 行为 | 版本记录 |
|---|---|---|
| `strict`（默认） | 只基于检索证据写作，每段带 `[En]` 引用；检索不到证据直接返回「资料不足」，不硬写 | `lesson_versions.mode='strict'` |
| `loose` | 允许模型基于自身通用知识自由写作，证据仅作可选参考；正文首行强制注入「⚠️ 本文由大模型编写，未经知识库证据核实」声明 | `lesson_versions.mode='loose'` |

`lessons.last_mode` 跟随最近一次生成模式，`generate` / `amend` 的返回体都带 `mode`，便于前端提示当前正文的可信度来源。

---

## 路线图

- **M0**：单机跑通核心闭环（生成单讲 + 追问 + 修改 + 文档历史），RAG 最小链路。
- **M1**：课程蓝图 + 逐讲审核 + 阅读器 + 术语表/学习路径。
- **M2**：多租户 + RBAC + 多作者协同 + 配额。
- **M3**：任务队列化 + 分布式 SSE + 对象存储。
- **M4**：AI 生图/搜图 + 导出 EPUB/PDF（中文字体内嵌）。
- **M5**：沙箱实跑 + 可观测 + K8s Helm。

> 自 M0 起即按 Port/Adapter 编写，避免后期返工。
