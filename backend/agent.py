"""
考研英语二 AI Agent 核心逻辑

核心职责：
1. 管理 LLM 客户端（OpenAI 兼容 API）
2. 构建对话上下文（系统提示词 + 混合记忆检索）
3. 流式调用 LLM 并实时返回响应
4. 管理多用户会话（创建、查询、清除）
5. 持久化存储：JSON 文件 + FAISS 向量索引

记忆系统架构（先进混合检索）：
┌─────────────────────────────────────────────┐
│              对话上下文构建                    │
│  system_prompt + summary + retrieved + recent │
├─────────────────────────────────────────────┤
│  summary    ← 定期 LLM 压缩旧对话摘要          │
│  retrieved  ← FAISS 余弦相似度语义检索 Top-K   │
│  recent     ← 最近 5 轮（时间局部性）          │
│  current    ← 用户当前消息                     │
└─────────────────────────────────────────────┘

依赖：
- openai >= 1.0（异步客户端 + Embedding API）
- faiss-cpu（Facebook 向量相似度搜索引擎）
- numpy（向量运算）
- prompts 模块（题型提示词映射）
"""

import os
import json
import threading
import asyncio
import pickle
from pathlib import Path
from typing import AsyncGenerator

import numpy as np
import faiss
from openai import AsyncOpenAI

try:
    from .prompts import QUESTION_TYPE_PROMPTS, BASE_SYSTEM_PROMPT
except ImportError:
    from prompts import QUESTION_TYPE_PROMPTS, BASE_SYSTEM_PROMPT

# ============================================================
# 配置常量
# ============================================================
EMBEDDING_DIM = 1536          # OpenAI text-embedding-3-small 默认维度
RETRIEVAL_TOP_K = 5           # 语义检索返回最相似的 K 条
RECENT_WINDOW = 5             # 始终保留最近 N 轮
SUMMARY_INTERVAL = 10         # 每 N 轮触发一次摘要生成
SUMMARY_MAX_TOKENS = 200      # 摘要最大 token 数


# ============================================================
# 向量记忆引擎
# ============================================================

class VectorMemory:
    """基于 FAISS 的长时语义记忆

    核心能力：
    - 文本 → embedding → 存入 FAISS 索引
    - 根据当前查询语义检索最相关的历史对话
    - 定期生成对话摘要，压缩旧历史
    - 持久化到磁盘（重启后恢复记忆）

    工作原理：
    1. 每轮对话结束后，将 (user_msg, ai_msg) 拼接 → embedding → 写入 FAISS
    2. 下一轮对话时，取当前 user_msg → embedding → FAISS.search() → Top-K 相关历史
    3. 每 N 轮触发 LLM 摘要：将全部对话压缩为一段摘要文本
    4. 索引和摘要保存为 .faiss 和 .faiss_meta 文件
    """

    def __init__(self, client: AsyncOpenAI, model: str, sid: str, data_dir: Path):
        self._client = client
        self._model = model
        self._sid = sid
        self._data_dir = data_dir
        self._lock = threading.Lock()

        # FAISS 内积索引（向量归一化后等价于余弦相似度）
        self._index = faiss.IndexFlatIP(EMBEDDING_DIM)
        self._texts: list[dict] = []      # 与 index 行对应的消息对
        self._summary: str = ""           # 定期压缩的对话摘要
        self._round_count = 0             # 对话轮数计数器

        # 启动时恢复持久化数据
        self._load()

    # ----------------------------------------------------------
    # 索引文件路径
    # ----------------------------------------------------------
    @property
    def _index_path(self) -> Path:
        return self._data_dir / f"mem_{self._sid}.faiss"

    @property
    def _meta_path(self) -> Path:
        return self._data_dir / f"mem_{self._sid}.faiss_meta"

    # ----------------------------------------------------------
    # 持久化
    # ----------------------------------------------------------
    def _load(self):
        """从磁盘恢复 FAISS 索引和元数据"""
        if not self._index_path.exists():
            return
        try:
            self._index = faiss.read_index(str(self._index_path))
            with open(self._meta_path, "rb") as f:
                meta = pickle.load(f)
            self._texts = meta.get("texts", [])
            self._summary = meta.get("summary", "")
            self._round_count = meta.get("round_count", self._index.ntotal)
        except (OSError, pickle.PickleError, RuntimeError):
            pass

    def _save(self):
        """将 FAISS 索引和元数据写入磁盘（异步线程）"""
        def _write():
            with self._lock:
                try:
                    faiss.write_index(self._index, str(self._index_path))
                    meta = {
                        "texts": self._texts,
                        "summary": self._summary,
                        "round_count": self._round_count,
                    }
                    with open(self._meta_path, "wb") as f:
                        pickle.dump(meta, f)
                except OSError:
                    pass
        threading.Thread(target=_write, daemon=True).start()

    # ----------------------------------------------------------
    # 核心 API
    # ----------------------------------------------------------

    async def embed(self, text: str) -> np.ndarray | None:
        """调用 Embedding API 将文本转为向量（已归一化）

        如果 API 不支持 embedding（如 DeepSeek），返回 None，上层调用者会优雅降级。
        """
        try:
            resp = await self._client.embeddings.create(
                model=self._model,
                input=text,
            )
            vec = np.array(resp.data[0].embedding, dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            return vec
        except Exception:
            return None

    async def add_exchange(self, user_msg: str, ai_msg: str):
        """将一轮对话存入向量索引（embedding 不可用时跳过）"""
        text = f"用户：{user_msg}\n助手：{ai_msg}"
        vec = await self.embed(text)
        if vec is None:
            return  # embedding 不可用，跳过向量存储
        self._index.add(vec.reshape(1, -1))
        self._texts.append({"role": "user", "content": user_msg, "ai": ai_msg})
        self._round_count += 1
        self._save()

    async def retrieve(self, query: str, k: int = RETRIEVAL_TOP_K) -> list[dict]:
        """语义检索与当前查询最相关的历史对话（embedding 不可用时返回空）"""
        if self._index.ntotal == 0:
            return []
        k = min(k, self._index.ntotal)
        q_vec = await self.embed(query)
        if q_vec is None:
            return []
        distances, indices = self._index.search(q_vec.reshape(1, -1), k)
        results = []
        for i in indices[0]:
            if 0 <= i < len(self._texts):
                results.append(self._texts[i])
        return results

    async def maybe_summarize(self):
        """每隔 SUMMARY_INTERVAL 轮，用 LLM 压缩全部历史为摘要"""
        if self._round_count == 0 or self._round_count % SUMMARY_INTERVAL != 0:
            return
        if not self._texts:
            return

        # 构建摘要提示词
        history_text = ""
        for t in self._texts[-30:]:  # 只取最近 30 条做摘要输入
            history_text += f"用户：{t['content'][:200]}\n助手：{t.get('ai', '')[:200]}\n"

        prompt = (
            "你是对话摘要专家。请将以下对话历史压缩为一段简短摘要（200字以内），"
            "保留关键信息、用户偏好、重要知识点和未完成的任务。\n\n"
            f"{history_text}\n\n摘要："
        )
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=SUMMARY_MAX_TOKENS,
            )
            self._summary = resp.choices[0].message.content.strip()
            self._save()
        except Exception:
            pass  # 摘要失败不影响主流程

    @property
    def summary(self) -> str:
        return self._summary

    @property
    def history(self) -> list[dict]:
        """返回原始消息列表（供 _fallback_title 等使用）"""
        result = []
        for t in self._texts:
            result.append({"role": "user", "content": t["content"]})
            result.append({"role": "assistant", "content": t.get("ai", "")})
        return result


# ============================================================
# AI Agent
# ============================================================

class EnglishAgent:
    """考研英语二学习助手 AI Agent

    会话管理：
    - 存储结构 {session_id: {"title": "...", "messages": [...]}}
    - title 由 LLM 根据首轮对话内容自动生成（15 字以内）
    - 每次对话自动保存到 JSON 文件

    记忆系统（混合检索）：
    - 近期窗口：始终保留最近 RECENT_WINDOW 轮
    - 语义检索：通过 FAISS 余弦相似度检索 Top-K 相关历史
    - 摘要压缩：定期用 LLM 压缩旧对话为摘要
    - 持久化：FAISS 索引 + pickle 元数据，重启恢复

    LLM 调用：
    - 使用 OpenAI 兼容 API（支持 DeepSeek、OpenAI 等）
    - 流式输出（Streaming），逐 chunk 返回给前端
    - temperature=0.7，max_tokens=4096
    """

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY", "sk-your-api-key"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1"),
            timeout=120.0,
        )
        self.model = os.getenv("OPENAI_MODEL", "deepseek-chat")
        self.embedding_model = os.getenv(
            "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
        )

        # 持久化路径
        self._data_file = Path(__file__).resolve().parent.parent / "sessions.json"
        self._mem_dir = Path(__file__).resolve().parent.parent / "memory"
        self._mem_dir.mkdir(parents=True, exist_ok=True)
        self._save_lock = threading.Lock()

        # 会话存储
        self.sessions: dict[str, dict] = {}

        # 向量记忆字典（每个 session 一个 VectorMemory）
        self._memories: dict[str, VectorMemory] = {}

        # 启动时恢复
        self._load_sessions()

    # ------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------

    def _load_sessions(self):
        """从 sessions.json 恢复历史会话（支持新旧格式自动迁移）"""
        if not self._data_file.exists():
            return
        try:
            with open(self._data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            for sid, val in data.items():
                if isinstance(val, list):
                    title = self._fallback_title(val)
                    self.sessions[sid] = {"title": title, "messages": val}
                elif isinstance(val, dict) and "messages" in val:
                    self.sessions[sid] = val
        except (json.JSONDecodeError, OSError):
            pass

        # 为每个已恢复的 session 初始化 VectorMemory
        for sid in self.sessions:
            self._get_memory(sid)

    def _save_sessions(self):
        """异步线程保存 sessions.json（原子写入）"""
        def _write():
            with self._save_lock:
                try:
                    tmp = self._data_file.with_suffix(".tmp")
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(self.sessions, f, ensure_ascii=False, indent=2)
                    tmp.replace(self._data_file)
                except OSError:
                    pass
        threading.Thread(target=_write, daemon=True).start()

    # ------------------------------------------------------------
    # 会话管理
    # ------------------------------------------------------------

    def _get_memory(self, session_id: str) -> VectorMemory:
        """获取或创建会话的向量记忆实例"""
        if session_id not in self._memories:
            self._memories[session_id] = VectorMemory(
                client=self.client,
                model=self.embedding_model,
                sid=session_id,
                data_dir=self._mem_dir,
            )
        return self._memories[session_id]

    def _get_session(self, session_id: str) -> list[dict]:
        """获取或创建会话的消息列表"""
        if session_id not in self.sessions:
            self.sessions[session_id] = {"title": "新对话", "messages": []}
        return self.sessions[session_id]["messages"]

    def clear_session(self, session_id: str):
        """清除指定会话（JSON + FAISS 索引）"""
        if session_id in self.sessions:
            del self.sessions[session_id]
        if session_id in self._memories:
            mem = self._memories.pop(session_id)
            # 删除磁盘上的 FAISS 文件
            try:
                mem._index_path.unlink(missing_ok=True)
                mem._meta_path.unlink(missing_ok=True)
            except OSError:
                pass
        self._save_sessions()

    def get_session_history(self, session_id: str) -> list[dict]:
        """返回指定会话的完整消息历史"""
        return self._get_session(session_id)

    # ------------------------------------------------------------
    # 标题生成
    # ------------------------------------------------------------

    @staticmethod
    def _fallback_title(messages: list[dict]) -> str:
        """取首条用户消息作为标题（截取前 30 字）"""
        for m in messages:
            if m.get("role") == "user":
                content = m["content"]
                return content[:30] + ("..." if len(content) > 30 else "")
        return "新对话"

    # ------------------------------------------------------------
    # 系统提示词
    # ------------------------------------------------------------

    def _build_system_prompt(self, question_type: str | None) -> str:
        if question_type and question_type in QUESTION_TYPE_PROMPTS:
            return QUESTION_TYPE_PROMPTS[question_type]["prompt"]
        return BASE_SYSTEM_PROMPT

    def get_question_types(self) -> list[dict]:
        return [
            {"id": key, "name": val["name"], "icon": val["icon"],
             "description": val["description"]}
            for key, val in QUESTION_TYPE_PROMPTS.items()
        ]

    # ------------------------------------------------------------
    # 核心对话逻辑（混合记忆检索）
    # ------------------------------------------------------------

    async def chat(
        self,
        session_id: str,
        message: str,
        question_type: str | None = None,
        display_message: str = "",
    ) -> AsyncGenerator[str, None]:
        """执行一次对话并流式返回 AI 回复

        Args:
            message: 发送给 LLM 的消息（可能含 OCR 文本等增强内容）
            display_message: 展示/存储在会话历史中的原始消息（无 OCR 文本干扰）
        """
        session = self._get_session(session_id)
        memory = self._get_memory(session_id)
        system_prompt = self._build_system_prompt(question_type)

        # ----- 构建混合上下文 -----
        messages = [{"role": "system", "content": system_prompt}]

        # 1. 摘要（长期记忆压缩）
        if memory.summary:
            messages.append({
                "role": "system",
                "content": f"[历史对话摘要] {memory.summary}",
            })

        # 2. 语义检索结果（相关历史）
        retrieved = await memory.retrieve(message)
        if retrieved:
            messages.append({
                "role": "system",
                "content": "[以下是与你当前问题相关的历史对话]",
            })
            for r in retrieved:
                messages.append({"role": "user", "content": r["content"]})
                messages.append({"role": "assistant", "content": r.get("ai", "")})

        # 3. 近期窗口（时间局部性）
        recent = session[-(RECENT_WINDOW * 2):]  # *2 因为 user+assistant 成对
        messages.extend(recent)

        # 4. 当前消息
        messages.append({"role": "user", "content": message})

        # 保存用户消息到会话历史（display_message 非空用 display，否则用 message）
        stored = display_message if display_message else message
        session.append({"role": "user", "content": stored})

        # 首条消息 → 立即设置降级标题
        session_data = self.sessions.get(session_id)
        if session_data and len(session) == 1:
            session_data["title"] = self._fallback_title(session)
            self._save_sessions()

        # ----- 流式调用 LLM -----
        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                temperature=0.7,
                max_tokens=4096,
            )

            full_response = ""
            thinking_active = False
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta:
                    delta = chunk.choices[0].delta

                    # 推理模型思考过程 → 替换为"思考中..."
                    reasoning = getattr(delta, "reasoning_content", None) or ""
                    if reasoning:
                        if not thinking_active:
                            thinking_active = True
                            yield f"data: {json.dumps({'thinking': True, 'content': '思考中...', 'done': False})}\n\n"
                        continue

                    content = delta.content or ""
                    if content:
                        if thinking_active:
                            thinking_active = False
                            yield f"data: {json.dumps({'thinking': False, 'content': '', 'done': False})}\n\n"
                        full_response += content
                        yield f"data: {json.dumps({'content': content, 'done': False})}\n\n"

            # 保存 AI 回复到会话历史
            session.append({"role": "assistant", "content": full_response})
            self._save_sessions()

            # ----- 后台异步：向量记忆 + 摘要 -----
            asyncio.create_task(
                memory.add_exchange(message, full_response)
            )
            asyncio.create_task(memory.maybe_summarize())

            yield f"data: {json.dumps({'content': '', 'done': True})}\n\n"

        except Exception as e:
            error_msg = f"抱歉，出了点问题：{str(e)}。请检查 API 配置是否正确。"
            yield f"data: {json.dumps({'content': error_msg, 'done': True})}\n\n"


# 全局单例
agent = EnglishAgent()
