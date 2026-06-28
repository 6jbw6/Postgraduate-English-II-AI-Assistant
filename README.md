# 考研英语二 AI 学习助手

基于大语言模型（LLM）的考研英语二全题型智能辅导系统，搭载 FAISS 向量记忆引擎，实现长时语义记忆。

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
  sessions.json  ← 会话元数据 + 消息列表
  memory/*.faiss ← FAISS 向量索引 (重启恢复)
  memory/*.faiss_meta ← pickle 元数据 (文本+摘要+计数)
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | Vue 3 + Vite（KeepAlive 缓存 + IntersectionObserver 无限滚动）|
| 后端框架 | Python FastAPI + Uvicorn |
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
│   ├── main.py              # FastAPI 应用 + API 路由（含 .env 加载）
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
├── sessions.json            # 会话持久化文件（自动生成）
├── .env                     # 环境变量配置（API Key / 模型等）
├── .gitignore
└── README.md
```

## 快速开始

### 1. 环境要求

- Python >= 3.10
- Node.js >= 18

### 2. 配置环境变量

编辑项目根目录下的 `.env` 文件，填入你的 API 配置：
```env
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-v4-pro
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

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/question-types` | 获取题型列表 |
| POST | `/api/chat` | 对话接口（SSE 流式） |
| GET | `/api/sessions` | 获取所有历史会话列表（含标题、预览） |
| GET | `/api/session/{id}` | 获取指定会话消息（支持 `?offset=0&limit=10` 分页，返回 `has_more`）|
| DELETE | `/api/session/{id}` | 清除指定会话（JSON + FAISS 索引） |

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
