"""
考研英语二 AI Agent 核心逻辑

核心职责：
1. 管理 LLM 客户端（OpenAI 兼容 API）
2. 构建对话上下文（系统提示词 + 混合记忆检索）
3. 流式调用 LLM 并实时返回响应
4. 管理向量记忆（FAISS 语义检索 + LLM 摘要）

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

会话持久化由 main.py 通过数据库管理，本模块只负责 LLM 调用 + 向量记忆。
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
    from .config import settings
except ImportError:
    from prompts import QUESTION_TYPE_PROMPTS, BASE_SYSTEM_PROMPT
    from config import settings

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
    """

    def __init__(self, client: AsyncOpenAI, model: str, sid: str, data_dir: Path):
        self._client = client
        self._model = model
        self._sid = sid
        self._data_dir = data_dir
        self._lock = threading.Lock()

        self._index = faiss.IndexFlatIP(EMBEDDING_DIM)
        self._texts: list[dict] = []
        self._summary: str = ""
        self._round_count = 0

        self._load()

    @property
    def _index_path(self) -> Path:
        return self._data_dir / f"mem_{self._sid}.faiss"

    @property
    def _meta_path(self) -> Path:
        return self._data_dir / f"mem_{self._sid}.faiss_meta"

    def _load(self):
        """从磁盘恢复 FAISS 索引和配套元数据；失败时降级为空记忆。"""
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
        """异步落盘，避免每次对话结束时阻塞主请求链路。"""
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

    async def embed(self, text: str) -> np.ndarray | None:
        """生成归一化向量；归一化后内积搜索等价于余弦相似度搜索。"""
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
        """把一轮完整问答加入长期语义记忆。"""
        text = f"用户：{user_msg}\n助手：{ai_msg}"
        vec = await self.embed(text)
        if vec is None:
            return
        self._index.add(vec.reshape(1, -1))
        self._texts.append({"role": "user", "content": user_msg, "ai": ai_msg})
        self._round_count += 1
        self._save()

    async def retrieve(self, query: str, k: int = RETRIEVAL_TOP_K) -> list[dict]:
        """按语义相似度召回与当前问题最相关的历史片段。"""
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
        """每隔固定轮次压缩近期对话，降低后续上下文长度。"""
        if self._round_count == 0 or self._round_count % SUMMARY_INTERVAL != 0:
            return
        if not self._texts:
            return

        history_text = ""
        for t in self._texts[-30:]:
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
            pass

    @property
    def summary(self) -> str:
        return self._summary


# ============================================================
# AI Agent
# ============================================================

class EnglishAgent:
    """考研英语二学习助手 AI Agent

    会话管理由外部（main.py + 数据库）负责。
    本类只负责 LLM 上下文构建 + 流式调用 + 向量记忆。
    """

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key or "sk-your-api-key",
            base_url=settings.openai_base_url,
            timeout=settings.openai_timeout_seconds,
        )
        self.model = settings.openai_model
        self.embedding_model = settings.openai_embedding_model

        self._mem_dir = settings.memory_dir
        self._mem_dir.mkdir(parents=True, exist_ok=True)

        self._memories: dict[str, VectorMemory] = {}
        self._chat_semaphore = asyncio.Semaphore(settings.llm_max_concurrency)

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

    def clear_memory(self, session_id: str):
        """清除某会话的向量记忆"""
        if session_id in self._memories:
            mem = self._memories.pop(session_id)
            try:
                mem._index_path.unlink(missing_ok=True)
                mem._meta_path.unlink(missing_ok=True)
            except OSError:
                pass

    # ------------------------------------------------------------
    # 系统提示词
    # ------------------------------------------------------------

    def _build_system_prompt(self, question_type: str | None) -> str:
        """根据题型选择专用提示词；没有题型时使用通用助手提示词。"""
        if question_type and question_type in QUESTION_TYPE_PROMPTS:
            return QUESTION_TYPE_PROMPTS[question_type]["prompt"]
        return BASE_SYSTEM_PROMPT

    def get_question_types(self) -> list[dict]:
        """返回前端题型菜单需要的元数据。"""
        return [
            {"id": key, "name": val["name"], "icon": val["icon"],
             "description": val["description"]}
            for key, val in QUESTION_TYPE_PROMPTS.items()
        ]

    # ------------------------------------------------------------
    # 核心对话逻辑
    # ------------------------------------------------------------

    async def chat(
        self,
        session_id: str,
        message: str,
        history: list[dict] | None = None,
        question_type: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """执行一次对话并流式返回 AI 回复

        Args:
            session_id: 会话 ID
            message: 发送给 LLM 的消息（可能含 OCR 文本等增强内容）
            history: 来自数据库的消息历史 [{"role": "user/assistant", "content": "..."}, ...]
            question_type: 题型标识
        """
        memory = self._get_memory(session_id)
        system_prompt = self._build_system_prompt(question_type)
        history = history or []

        # ----- 构建混合上下文 -----
        # 顺序很重要：系统提示词先定角色，其次补摘要和语义召回，最后放近期上下文与当前问题。
        messages = [{"role": "system", "content": system_prompt}]

        # 1. 摘要：提供长期背景，体积小但信息密度高。
        if memory.summary:
            messages.append({
                "role": "system",
                "content": f"[历史对话摘要] {memory.summary}",
            })

        # 2. 语义检索：补充和当前问题最相关的历史细节。
        retrieved = await memory.retrieve(message)
        if retrieved:
            messages.append({
                "role": "system",
                "content": "[以下是与你当前问题相关的历史对话]",
            })
            for r in retrieved:
                messages.append({"role": "user", "content": r["content"]})
                messages.append({"role": "assistant", "content": r.get("ai", "")})

        # 3. 近期窗口：保留最近几轮原文，保证短期连续性。
        recent = history[-(RECENT_WINDOW * 2):]
        messages.extend(recent)

        # 4. 当前消息：必须放在最后，确保模型把它当作本轮任务。
        messages.append({"role": "user", "content": message})

        # ----- 流式调用 LLM -----
        try:
            async with self._chat_semaphore:
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

            # 后台异步：向量记忆 + 摘要，不阻塞 SSE 响应收尾。
            asyncio.create_task(memory.add_exchange(message, full_response))
            asyncio.create_task(memory.maybe_summarize())

            yield f"data: {json.dumps({'content': '', 'done': True})}\n\n"

        except Exception as e:
            error_msg = f"抱歉，出了点问题：{str(e)}。请检查 API 配置是否正确。"
            yield f"data: {json.dumps({'content': error_msg, 'done': True})}\n\n"


# 全局单例
agent = EnglishAgent()
