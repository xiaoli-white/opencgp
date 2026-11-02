# AI 课程工作室

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

---

## 路线图

- **M0**：单机跑通核心闭环（生成单讲 + 追问 + 修改 + 文档历史），RAG 最小链路。
- **M1**：课程蓝图 + 逐讲审核 + 阅读器 + 术语表/学习路径。
- **M2**：多租户 + RBAC + 多作者协同 + 配额。
- **M3**：任务队列化 + 分布式 SSE + 对象存储。
- **M4**：AI 生图/搜图 + 导出 EPUB/PDF（中文字体内嵌）。
- **M5**：沙箱实跑 + 可观测 + K8s Helm。

> 自 M0 起即按 Port/Adapter 编写，避免后期返工。
