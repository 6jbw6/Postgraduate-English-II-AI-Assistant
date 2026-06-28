"""
考研英语二 AI 学习助手 - FastAPI 后端服务

功能模块：
- /api/health           健康检查
- /api/question-types   获取题型列表
- /api/chat             对话接口（流式 SSE）
- /api/session/{id}     会话管理（查看/删除）

启动方式：
    cd 项目根目录
    python backend/main.py
    或: uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

前端资源：
    开发模式：前端使用 Vite 开发服务器（npm run dev），后端仅提供 API
              跨域已通过 CORS 中间件处理
    生产模式：前端构建后（npm run build）将产物输出到 frontend/dist/
              后端会自动提供静态文件服务
"""

import os
import sys
import uuid
import json
import base64
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager

# OCR 依赖（图片文字识别）
import logging
logger = logging.getLogger("uvicorn")

_ocr_reader = None
HAS_OCR = False


def _init_ocr():
    """延迟初始化 easyocr（避免阻塞启动，并捕获错误日志）"""
    global _ocr_reader, HAS_OCR
    try:
        import easyocr
        logger.info("正在加载 easyocr 英文识别模型（首次约30秒）...")
        _ocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        HAS_OCR = True
        logger.info("easyocr 初始化完成")
    except Exception as e:
        logger.warning(f"easyocr 初始化失败：{e}。图片 OCR 功能不可用。")


# ============================================================
# FastAPI 应用
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化 OCR"""
    import threading
    threading.Thread(target=_init_ocr, daemon=True).start()
    yield

app = FastAPI(title="考研英语二 AI 学习助手", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 加载 .env 文件（项目根目录）
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _val = _line.split("=", 1)
                os.environ.setdefault(_key.strip(), _val.strip())


# ============================================================
# Agent 导入（兼容直接运行和模块运行）
# ============================================================

try:
    from backend.agent import agent
    _APP_MODULE = "backend.main:app"
except ImportError:
    from agent import agent
    _APP_MODULE = "main:app"


# ============================================================
# Pydantic 模型
# ============================================================

class ChatRequest(BaseModel):
    session_id: str = ""                # 会话 ID，首次对话传空字符串
    message: str = ""                   # 用户消息
    question_type: str | None = None    # 可选，指定题型
    images: list[str] | None = None     # 可选，base64 图片数组



# ============================================================
# 图片 OCR 工具函数
# ============================================================

def ocr_image(b64_data: str) -> str:
    """对 base64 图片执行 OCR 文字识别（使用 easyocr）

    easyocr 是纯 Python 深度学习 OCR 引擎，基于 PyTorch，
    无需安装 Tesseract 等外部依赖。
    """
    if not HAS_OCR or _ocr_reader is None:
        logger.debug("OCR 不可用：HAS_OCR=%s", HAS_OCR)
        return ""
    try:
        img_bytes = base64.b64decode(b64_data)
        results = _ocr_reader.readtext(img_bytes, detail=0)
        text = " ".join(results)
        logger.info("OCR 识别结果：%d 段文字，共 %d 字", len(results), len(text))
        return text
    except Exception as e:
        logger.warning("OCR 识别失败：%s", e)
        return ""


def _reformat_quiz_options(text: str) -> str:
    """将 OCR 识别出的选择题选项重新排版为每行一题的格式

    OCR 经常把"1. A. xxx B. xxx C. xxx D. xxx"拆成多行，
    此函数尝试将它们合并为每行一道完整题目的格式。
    """
    import re
    lines = text.split("\n")
    result = []
    buffer = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if buffer:
                result.append(buffer)
                buffer = ""
            continue
        # 检测是否以题号开头
        if re.match(r"^\d+[\.\、\)]", stripped):
            if buffer:
                result.append(buffer)
            buffer = stripped
        else:
            if buffer:
                buffer += " " + stripped
            else:
                result.append(stripped)
    if buffer:
        result.append(buffer)
    return "\n".join(result)


# ============================================================
# API 路由
# ============================================================

@app.get("/api/health")
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "ocr_available": HAS_OCR,
    }


@app.get("/api/question-types")
async def get_question_types():
    """获取题型列表"""
    return {"types": agent.get_question_types()}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """核心对话接口（Server-Sent Events 流式响应）

    支持图片 OCR：如果附带 image (base64)，先识别图片中的英文文字，
    拼入消息前缀发送给 LLM。DeepSeek 等不支持多模态的模型也能"看懂"图片。

    处理流程：
    1. 生成或复用 session_id
    2. 如有图片，OCR 提取文字 → 拼入消息
    3. 校验最终消息非空
    4. 流式调用 Agent.chat()
    """
    session_id = request.session_id or str(uuid.uuid4())
    user_message = request.message.strip()  # 原始用户消息（展示用）
    llm_message = user_message              # 发送给 LLM 的消息

    # 图片 OCR：逐张识别，拼入 LLM 消息，原始消息保持不变
    if request.images:
        all_texts = []
        for i, b64 in enumerate(request.images):
            text = ocr_image(b64)
            if text:
                # 后处理：将四选一选项分行重新合并为每行一题
                text = _reformat_quiz_options(text)
                all_texts.append(f"[图{i + 1}]\n{text}")
        if all_texts:
            # 图表作文：使用图表专用提示词
            if request.question_type == "writing_b" and not user_message:
                prefix = (
                    "[用户上传了一张图表/表格的图片，以下是 OCR 识别到的所有文字内容。"
                    "你需要：\n"
                    "1. 根据这些文字还原图表的数据结构（标题、横轴/纵轴、图例、数值等）\n"
                    "2. 用文字描述图表内容（趋势、对比、占比等）\n"
                    "3. 按照英语二大作文三段式要求，分析原因并给出评论\n\n"
                    "图片中的原始文字内容：\n"
                )
                llm_message = prefix + "\n\n".join(all_texts)
            else:
                prefix = f"[用户上传了{len(request.images)}张图片，以下是识别到的文字内容]\n\n"
                if user_message:
                    llm_message = prefix + "\n\n".join(all_texts) + f"\n\n[用户的补充说明] {user_message}"
                else:
                    llm_message = prefix + "\n\n".join(all_texts)
        elif not user_message:
            raise HTTPException(status_code=400, detail="图片中未识别到文字，且未提供文本消息")

    if not llm_message:
        raise HTTPException(status_code=400, detail="消息不能为空")

    logger.info("对话请求：session=%s, user_msg=%s, images=%d, llm_msg_len=%d",
                session_id, user_message[:50] if user_message else "(空)",
                len(request.images) if request.images else 0, len(llm_message))

    async def generate():
        """SSE 事件生成器"""
        yield f"data: {json.dumps({'session_id': session_id, 'content': '', 'done': False})}\n\n"

        async for chunk in agent.chat(
            session_id=session_id,
            message=llm_message,
            display_message=user_message,  # 会话中存储原始消息
            question_type=request.question_type,
        ):
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/sessions")
async def list_sessions():
    """获取所有历史会话列表（含标题、预览）"""
    sessions = []
    for sid, data in agent.sessions.items():
        sessions.append({
            "session_id": sid,
            "title": data.get("title", "新对话"),
            "message_count": len(data.get("messages", [])),
        })
    # 按最近活跃排序（简化：保持字典顺序）
    sessions.reverse()
    return {"sessions": sessions}


@app.delete("/api/session/{session_id}")
async def clear_session(session_id: str):
    """清除指定会话（JSON + FAISS 索引）"""
    agent.clear_session(session_id)
    return {"status": "ok"}


@app.get("/api/session/{session_id}")
async def get_session(
    session_id: str,
    offset: int = 0,
    limit: int = 10,
):
    """获取指定会话消息（支持分页）

    Args:
        offset: 起始偏移量
        limit: 每页条数（默认 10）
    Returns:
        {session_id, messages, has_more}
    """
    all_msgs = agent.get_session_history(session_id)
    total = len(all_msgs)

    # 从末尾倒排取分页
    start = max(0, total - offset - limit)
    end = total - offset
    page = all_msgs[start:end]
    has_more = start > 0

    return {
        "session_id": session_id,
        "messages": page,
        "has_more": has_more,
    }


# ============================================================
# 生产模式：前端静态文件服务
# ============================================================

_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if _frontend_dist.exists():
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """生产模式下提供前端静态文件"""
        # API 路径不在这里处理
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)

        file_path = _frontend_dist / (full_path or "index.html")
        if file_path.is_file():
            return FileResponse(file_path)

        # SPA fallback
        index_path = _frontend_dist / "index.html"
        if index_path.exists():
            return FileResponse(index_path)

        raise HTTPException(status_code=404)


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("  考研英语二 AI 学习助手")
    print("=" * 50)
    print("  后端地址: http://localhost:8000")
    print("  API 文档: http://localhost:8000/docs")
    print()

    import uvicorn

    uvicorn.run(
        _APP_MODULE,
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
