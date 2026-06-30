# 考研英语二 AI 学习助手

基于大语言模型（LLM）的考研英语二全题型智能辅导系统，搭载 FAISS 向量记忆引擎，实现长时语义记忆。当前版本已加入多用户认证、数据库持久化、统一配置、限流、健康检查和容器化部署能力。

## 功能特色

- **题型即对话**：自由对话、完形填空、阅读理解A/B、翻译、小作文、大作文各为一个独立对话，切换不中断 AI 思考
- **AI 对话辅导**：支持出题、讲解、批改、答疑、技巧分享
- **流式响应**：SSE 实时流式输出，打字机效果
- **混合记忆检索**：FAISS 语义检索 + LLM 摘要压缩 + 近期窗口，长对话不失忆
- **无限滚动分页**：消息列表顶部上滑加载更早历史，每次 10 条
- **图片上传**：支持粘贴或选择图片（最多9张），easyocr 深度学习引擎自动识别英文文字，DeepSeek 等非多模态模型也能"看懂"图片
- **Markdown 渲染**：基于 marked 库 (GFM 规范)，支持表格、任务列表、删除线等全语法
- **响应式设计**：适配桌面端和移动端
- **持久化记忆**：重启项目后对话历史、FAISS 索引、摘要全部恢复，自动加载最近 10 条消息
- **企业级运行能力**：JWT 认证、RBAC 权限、审计日志、Redis 限流/缓存、CORS 白名单、请求 ID、结构化日志、安全响应头、请求体大小限制、分层健康检查、Alembic 迁移、对象存储、Docker Compose、GitHub Actions CI

## 记忆系统架构

```
┌─────────────────────────────────────────────┐
│            对话上下文构建 (每次请求)          │
│  system_prompt + summary + retrieved + recent │
├─────────────────────────────────────────────┤
│  summary    ← LLM 定期压缩旧对话摘要 (每10轮)  │
│  retrieved  ← FAISS 余弦相似度语义检索 Top-5   │
│  recent     ← 最近 5 轮原始对话 (时间局部性)    │
│  current    ← 用户当前消息                     │
└─────────────────────────────────────────────┘

持久化层:
  MySQL          ← 用户、会话、消息、审计日志
  memory/*.faiss ← FAISS 向量索引 (重启恢复)
  memory/*.faiss_meta ← pickle 元数据 (文本+摘要+计数)
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | Vue 3 + Vite（KeepAlive 缓存 + IntersectionObserver 无限滚动）|
| 后端框架 | Python FastAPI + Uvicorn + SQLAlchemy |
| AI 对话 | OpenAI 兼容 API（支持 DeepSeek、OpenAI 等），SSE 流式 |
| LLM 记忆 | FAISS 向量索引 + Embedding 语义检索 + 定期摘要压缩 |
| 图片 OCR | easyocr (PyTorch 深度学习，纯 Python，零外部依赖) |
| Markdown 渲染 | marked v15 (GFM 规范) |
| 向量化 | OpenAI Embedding API (text-embedding-3-small) |

> **注意**：当前配置使用 DeepSeek，其不支持 Embedding API，语义检索自动降级跳过，摘要压缩仍正常工作。换用 OpenAI 后可启用完整的向量检索。

## 项目结构

```
├── backend/                 # 后端
│   ├── __init__.py
│   ├── main.py              # FastAPI 应用 + API 路由
│   ├── config.py            # 统一环境变量配置
│   ├── auth.py              # JWT 认证与密码哈希
│   ├── database.py          # SQLAlchemy 异步数据库模型
│   ├── middleware.py        # 请求追踪与安全响应头
│   ├── rate_limit.py        # 请求限流
│   ├── cache.py             # Redis 缓存抽象（自动降级）
│   ├── storage.py           # 本地/S3 对象存储抽象
│   ├── schemas.py           # Pydantic 请求/响应模型
│   ├── agent.py             # AI Agent 核心逻辑（混合记忆、LLM 调用）
│   ├── prompts.py           # 各题型系统提示词
│   └── requirements.txt     # Python 依赖（含 faiss-cpu, numpy）
├── frontend/                # 前端（Vue 3 + Vite）
│   ├── index.html           # Vite 入口 HTML
│   ├── package.json
│   ├── vite.config.js       # Vite 配置（含 API 代理）
│   ├── dist/                # 前端构建产物
│   └── src/
│       ├── main.js          # Vue 应用入口
│       ├── App.vue          # 根组件（题型→独立对话路由，首页）
│       ├── style.css        # 全局样式 / CSS 变量
│       ├── utils/
│       │   └── markdown.js  # Markdown 渲染（基于 marked 库）
│       └── components/
│           ├── Sidebar.vue      # 侧边栏（题型选择 + 清空对话）
│           ├── ChatArea.vue     # 聊天主区域（无限滚动 + 图片上传）
│           └── MessageBubble.vue # 消息气泡（图片网格 + 全屏预览）
├── memory/                  # FAISS 向量索引持久化目录（自动创建）
├── data/                    # 本地上传文件/临时数据目录（自动生成，不提交）
├── migrations/              # Alembic 数据库迁移
├── .github/workflows/ci.yml # GitHub Actions CI
├── .env                     # 环境变量配置（API Key / 模型等）
├── .env.example             # 环境变量模板
├── Dockerfile               # 前后端多阶段构建镜像
├── docker-compose.yml       # 单机部署编排
├── .gitignore
└── README.md
```

## 快速开始

### 1. 环境要求

- Python >= 3.10
- Node.js >= 18
- MySQL 8.x（Docker 部署会自动启动 MySQL 服务）

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填入你的 API 配置：
```env
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
JWT_SECRET_KEY=change-this-to-a-long-random-secret-at-least-32-chars
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
DATABASE_URL=mysql+aiomysql://english_user:english_password@localhost:3306/english_ii?charset=utf8mb4
```

### 3. 安装依赖

```bash
# 后端
cd backend
pip install -r requirements.txt

# 前端
cd ../frontend
npm install
```

### 4. 启动服务

**开发模式**（推荐）：

```bash
# 终端 1：启动后端（端口 8000）
# 方式一：在项目根目录执行
py backend/main.py
# 方式二：在 backend 目录直接执行
cd backend && py main.py
# 或: uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2：启动前端 Vite 开发服务器（端口 5173）
cd frontend
npm run dev
```

然后访问 `http://localhost:5173`，Vite 会自动将 `/api` 请求代理到后端。

**生产模式**：

```bash
# 构建前端
cd frontend
npm run build

# 启动后端（会自动提供前端静态文件）
cd ..
py backend/main.py
```

访问 `http://localhost:8000` 即可。

**Docker 部署**：

```bash
docker compose up -d --build
docker compose logs -f
```

生产部署必须配置 `JWT_SECRET_KEY` 和 `MYSQL_ROOT_PASSWORD`，建议同时按实际域名设置 `CORS_ORIGINS`。容器会自行构建前端产物，并启动 MySQL、Redis、MinIO，不需要在宿主机提前执行 `npm run build`。

## 企业级配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_ENV` | `development` | 设置为 `production` 时强制校验 JWT 密钥 |
| `JSON_LOGS` | `false` | 是否输出 JSON 结构化访问日志 |
| `ACCESS_LOG_ENABLED` | `true` | 是否记录访问日志 |
| `MAX_REQUEST_BYTES` | `12582912` | 请求体大小上限，超限返回 413 |
| `JWT_SECRET_KEY` | 开发默认值 | 生产必须设置 32 位以上随机字符串 |
| `ADMIN_EMAILS` | 空 | 逗号分隔的管理员邮箱，注册时自动赋予 `admin` 角色 |
| `CORS_ORIGINS` | 本地 Vite 地址 | 逗号分隔的允许来源 |
| `DATABASE_URL` | `mysql+aiomysql://...` | MySQL 异步连接串，格式见 `.env.example` |
| `MYSQL_DATABASE` | `english_ii` | Docker Compose 内置 MySQL 数据库名 |
| `MYSQL_USER` | `english_user` | Docker Compose 内置 MySQL 应用用户 |
| `MYSQL_PASSWORD` | `english_password` | Docker Compose 内置 MySQL 应用用户密码 |
| `MYSQL_ROOT_PASSWORD` | 无 | Docker Compose 内置 MySQL root 密码，生产必须设置 |
| `REDIS_URL` | 空 | 配置后启用 Redis 限流与缓存，例如 `redis://redis:6379/0` |
| `CACHE_DEFAULT_TTL_SECONDS` | `300` | Redis 缓存默认 TTL |
| `OCR_ENABLED` | `true` | 是否加载 easyocr |
| `MAX_IMAGES_PER_REQUEST` | `9` | 单次请求图片数量上限 |
| `MAX_IMAGE_BYTES` | `8388608` | 单张图片大小上限 |
| `CHAT_RATE_LIMIT_PER_MINUTE` | `20` | 对话接口限流 |
| `AUTH_RATE_LIMIT_PER_MINUTE` | `10` | 登录/注册接口限流 |
| `STORAGE_BACKEND` | `local` | 对象存储后端：`local` 或 `s3` |
| `STORAGE_LOCAL_DIR` | `./data/uploads` | 本地上传文件目录 |
| `STORAGE_BASE_URL` | 空 | 对象访问基础 URL，例如 `https://cdn.example.com` |
| `S3_ENDPOINT_URL` | 空 | S3 兼容服务地址，MinIO 可填 `http://minio:9000` |
| `S3_BUCKET` | 空 | S3/MinIO bucket |
| `S3_ACCESS_KEY_ID` | 空 | S3 access key |
| `S3_SECRET_ACCESS_KEY` | 空 | S3 secret key |

## 企业架构能力

### Alembic 数据库迁移

项目保留开发环境启动自动建表，生产环境建议使用 Alembic 管理结构变更：

```bash
alembic upgrade head
alembic revision --autogenerate -m "change description"
```

首个迁移位于 `migrations/versions/20260630_0001_initial_enterprise_schema.py`，包含用户、会话、消息和审计日志表。

### Redis 限流与缓存

配置 `REDIS_URL` 后，限流从进程内存升级为 Redis 滑窗限流，支持多实例部署；题型列表等低频数据也会走 Redis 缓存。Redis 不可用时会自动降级到内存限流和空缓存。

### 高并发部署

建议生产环境至少做这些配置：

- `WEB_CONCURRENCY=2` 或更高，按 CPU 核数调整 Uvicorn worker 数
- `REDIS_URL=redis://...`，让限流和缓存跨进程生效
- `LLM_MAX_CONCURRENCY`，限制单个 worker 同时进行的流式 AI 请求，保护上游模型服务和本机内存
- `CHAT_HISTORY_MESSAGES_LIMIT`，控制每次对话加载的最近消息数，避免长会话拖慢查询和上下文构建
- `REDIS_MAX_CONNECTIONS`，限制缓存/限流占用的 Redis 连接数
- `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT_SECONDS`，调大数据库连接池
- MySQL 部署建议按 `WEB_CONCURRENCY * (DB_POOL_SIZE + DB_MAX_OVERFLOW)` 预估最大连接数，并同步调整 MySQL `max_connections`
- `OCR_MAX_CONCURRENCY`，限制 OCR 同时处理的图片数，避免 CPU 被打满
- 使用 MySQL + Alembic 迁移，不要依赖启动时自动建表
- 对象存储使用 S3/MinIO，避免大文件长期落数据库或本地磁盘

如果是容器编排，多副本应用建议前面挂负载均衡，后面统一接 Redis、数据库和对象存储。

### 对象存储

头像上传不再长期保存 Base64 到数据库。后端会将 Data URL 解码后写入对象存储，并在用户资料中保存 URL。

- `STORAGE_BACKEND=local`：保存到 `STORAGE_LOCAL_DIR`，通过 `/uploads/...` 访问
- `STORAGE_BACKEND=s3`：保存到 S3/MinIO，适合生产部署

### RBAC 与审计日志

用户表包含 `role` 字段，默认 `student`。可通过 `ADMIN_EMAILS=admin@example.com` 指定注册后自动成为管理员的邮箱。后端提供 `require_roles("admin")` 权限依赖，目前管理员接口包括：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/audit-logs` | 查看最近审计日志，需 `admin` 角色 |

注册、登录、资料更新、删除会话等关键操作会写入 `audit_logs`。

### CI/CD

`.github/workflows/ci.yml` 已包含：

- 后端单元测试
- 前端构建
- Docker 镜像构建检查

推送到 `main/master` 或创建 PR 时自动执行。

## 健康检查

| 路径 | 说明 |
|------|------|
| `GET /api/health` | 基础状态与版本信息 |
| `GET /api/health/live` | 进程存活检查 |
| `GET /api/health/ready` | 数据库可用性检查，适合容器健康探针 |

## 质量验证

```bash
py -m unittest discover -s backend\tests
py -c "import py_compile; [py_compile.compile(p, doraise=True) for p in ['backend/config.py','backend/schemas.py','backend/auth.py','backend/database.py','backend/rate_limit.py','backend/agent.py','backend/main.py']]"
cd frontend && npm run build
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/health/live` | 存活检查 |
| GET | `/api/health/ready` | 就绪检查（数据库） |
| GET | `/api/question-types` | 获取题型列表 |
| GET | `/api/v1/question-types` | 版本化 API，同 `/api/question-types` |
| POST | `/api/chat` | 对话接口（SSE 流式） |
| GET | `/api/sessions` | 获取所有历史会话列表（含标题、预览） |
| GET | `/api/session/{id}` | 获取指定会话消息（支持 `?offset=0&limit=10` 分页，返回 `has_more`）|
| DELETE | `/api/session/{id}` | 清除指定会话（JSON + FAISS 索引） |
| GET | `/api/admin/audit-logs` | 管理员审计日志 |

### 对话上下文构建流程

每次 `/api/chat` 请求，后端构建 LLM 上下文：

1. `system_prompt` — 题型专用提示词（完形/阅读/翻译/写作）
2. `[历史对话摘要]` — LLM 每 10 轮压缩的摘要（长期记忆）
3. `[相关历史对话]` — FAISS 语义检索 Top-5（中期记忆）
4. 最近 5 轮原始对话 — 时间局部性（短期记忆）
5. 当前用户消息（如有图片则自动 OCR 提取文字后拼入）

会话 ID 规则：`type_{题型}`（如 `type_cloze`、`type_reading_a`、`type_free`），每个题型独立记忆。

## 支持的 LLM 提供商

| 提供商 | BASE_URL | 推荐模型 |
|--------|----------|----------|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-v4-pro` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| 其他兼容 API | 自定 | 按服务商推荐 |

## License

MIT
