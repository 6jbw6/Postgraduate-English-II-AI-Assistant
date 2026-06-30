"""
考研英语二 AI 学习助手 - FastAPI 后端服务（企业版）

功能模块：
- /api/health           健康检查
- /api/question-types   获取题型列表
- /api/chat             对话接口（流式 SSE，需认证）
- /api/sessions         会话列表（需认证）
- /api/session/{id}     会话消息/删除（需认证）
- /api/auth/register    用户注册
- /api/auth/login       用户登录
- /api/auth/me          当前用户信息

启动方式：
    python backend/main.py
    或: uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import sys
import uuid
import json
import base64
import datetime
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager

try:
    from backend.config import settings
    from backend.middleware import RequestContextMiddleware
    from backend.cache import cache_get, cache_set
    from backend.storage import decode_data_url, storage
except ImportError:
    from config import settings
    from middleware import RequestContextMiddleware
    from cache import cache_get, cache_set
    from storage import decode_data_url, storage

# OCR 依赖
logger = logging.getLogger("uvicorn")

_ocr_reader = None
HAS_OCR = False


def _init_ocr():
    """延迟初始化 easyocr"""
    global _ocr_reader, HAS_OCR
    if not settings.ocr_enabled:
        logger.info("OCR 已通过 OCR_ENABLED=false 禁用")
        return
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
    """应用生命周期"""
    import threading
    # 初始化数据库表
    try:
        from backend.database import init_db
    except ImportError:
        from database import init_db
    init_db()
    logger.info("数据库表初始化完成")
    # 初始化 OCR
    threading.Thread(target=_init_ocr, daemon=True).start()
    yield


logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)

if settings.storage_backend.lower() == "local":
    app.mount("/uploads", StaticFiles(directory=str(settings.storage_local_dir)), name="uploads")


def _mount_versioned_api_routes() -> None:
    """把现有 /api 路由复制挂载到 /api/v1，兼容老前端同时提供版本化 API。"""
    router = APIRouter(prefix="/api/v1")
    for route in list(app.router.routes):
        path = getattr(route, "path", "")
        if not isinstance(route, APIRoute) or path == "/api/health" or not path.startswith("/api/"):
            continue
        router.add_api_route(
            path=path.removeprefix("/api"),
            endpoint=route.endpoint,
            response_model=route.response_model,
            status_code=route.status_code,
            tags=route.tags,
            dependencies=route.dependencies,
            summary=route.summary,
            description=route.description,
            response_description=route.response_description,
            responses=route.responses,
            deprecated=route.deprecated,
            methods=route.methods,
            operation_id=route.operation_id,
            response_model_include=route.response_model_include,
            response_model_exclude=route.response_model_exclude,
            response_model_by_alias=route.response_model_by_alias,
            response_model_exclude_unset=route.response_model_exclude_unset,
            response_model_exclude_defaults=route.response_model_exclude_defaults,
            response_model_exclude_none=route.response_model_exclude_none,
            include_in_schema=route.include_in_schema,
            response_class=route.response_class,
            name=route.name,
            callbacks=route.callbacks,
            openapi_extra=route.openapi_extra,
        )
    app.include_router(router)


# ============================================================
# 导入内部模块
# ============================================================

try:
    from backend.agent import agent
    from backend.database import AuditLog, get_db, User, Session as DBSession, Message
    from backend.auth import (
        get_current_user, get_optional_user, hash_password, verify_password,
        create_access_token, UserRegister, UserLogin, UserOut, UserProfileUpdate, TokenOut,
        require_roles, write_audit_log,
    )
    from backend.rate_limit import default_limit, chat_limit, auth_limit
    from backend.schemas import ChatRequest, SessionOut, SessionDetail, MessageOut
    _APP_MODULE = "backend.main:app"
except ImportError:
    # 兼容直接运行
    from agent import agent
    from database import AuditLog, get_db, User, Session as DBSession, Message
    from auth import (
        get_current_user, get_optional_user, hash_password, verify_password,
        create_access_token, UserRegister, UserLogin, UserOut, UserProfileUpdate, TokenOut,
        require_roles, write_audit_log,
    )
    from rate_limit import default_limit, chat_limit, auth_limit
    from schemas import ChatRequest, SessionOut, SessionDetail, MessageOut
    _APP_MODULE = "main:app"


# ============================================================
# 图片 OCR 工具函数
# ============================================================

def ocr_image(b64_data: str) -> str:
    """识别单张 Base64 图片中的英文文字；OCR 不可用时返回空字符串。"""
    if not HAS_OCR or _ocr_reader is None:
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
    """把 OCR 识别到的选项题文本尽量整理成按题号分行的格式。"""
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


def _fallback_title(messages: list[dict]) -> str:
    """取首条用户消息作为标题"""
    for m in messages:
        if m.get("role") == "user":
            content = m["content"]
            return content[:30] + ("..." if len(content) > 30 else "")
    return "新对话"


# ============================================================
# API: 通用
# ============================================================

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": settings.app_version, "ocr_available": HAS_OCR}


@app.get("/api/health/live")
async def liveness():
    return {"status": "alive"}


@app.get("/api/health/ready")
async def readiness(db: Annotated[AsyncSession, Depends(get_db)]):
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.exception("健康检查数据库不可用")
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ready"}


@app.get("/api/question-types", dependencies=[Depends(default_limit)])
async def get_question_types():
    cached = await cache_get("question-types", "all")
    if cached is not None:
        return cached
    payload = {"types": agent.get_question_types()}
    await cache_set("question-types", "all", payload)
    return payload


# ============================================================
# API: 认证
# ============================================================

@app.post("/api/auth/register", response_model=TokenOut, dependencies=[Depends(auth_limit)])
async def register(body: UserRegister, db: Annotated[AsyncSession, Depends(get_db)]):
    """用户注册"""
    # 检查用户名/邮箱是否已存在
    stmt = select(User).where((User.username == body.username) | (User.email == body.email))
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        field = "用户名" if existing.username == body.username else "邮箱"
        raise HTTPException(status_code=409, detail=f"{field}已被注册")

    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        role="admin" if body.email in settings.admin_emails else "student",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await write_audit_log(db, user.id, "auth.register", "user", body.email)

    token = create_access_token(user.id)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@app.post("/api/auth/login", response_model=TokenOut, dependencies=[Depends(auth_limit)])
async def login(body: UserLogin, db: Annotated[AsyncSession, Depends(get_db)]):
    """用户登录"""
    stmt = select(User).where(User.email == body.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    token = create_access_token(user.id)
    await write_audit_log(db, user.id, "auth.login", "user", body.email)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@app.get("/api/auth/me", response_model=UserOut, dependencies=[Depends(default_limit)])
async def get_me(current_user: Annotated[User, Depends(get_current_user)]):
    """获取当前登录用户信息"""
    return UserOut.model_validate(current_user)


@app.post("/api/profile", response_model=UserOut, dependencies=[Depends(default_limit)])
async def update_profile(
    body: UserProfileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """更新当前用户个人资料。"""
    return await _update_current_user_profile(body, current_user, db)


@app.patch("/api/auth/me", response_model=UserOut, dependencies=[Depends(default_limit)])
async def update_me(
    body: UserProfileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """更新当前用户个人资料"""
    return await _update_current_user_profile(body, current_user, db)


@app.post("/api/auth/me", response_model=UserOut, dependencies=[Depends(default_limit)])
async def update_me_post(
    body: UserProfileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """兼容 POST /api/auth/me 的个人资料更新接口。"""
    return await _update_current_user_profile(body, current_user, db)


@app.post("/api/auth/me/profile", response_model=UserOut, dependencies=[Depends(default_limit)])
async def update_me_profile(
    body: UserProfileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """兼容 POST 的个人资料更新接口，适配不允许 PATCH 的部署环境。"""
    return await _update_current_user_profile(body, current_user, db)


async def _update_current_user_profile(
    body: UserProfileUpdate,
    current_user: User,
    db: AsyncSession,
):
    """复用个人资料更新逻辑，多个兼容端点共用这一处。"""
    updates = body.model_dump(exclude_unset=True)
    avatar_url = updates.get("avatar_url")
    if isinstance(avatar_url, str) and avatar_url.startswith("data:image/"):
        content, mime_type = decode_data_url(avatar_url)
        stored = storage.save_bytes(content, mime_type, prefix=f"avatars/{current_user.id}")
        updates["avatar_url"] = stored.url

    for key, value in updates.items():
        setattr(current_user, key, value)

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    await write_audit_log(db, current_user.id, "user.profile.update", "user", str(current_user.id))
    return UserOut.model_validate(current_user)


@app.get("/api/admin/audit-logs", dependencies=[Depends(default_limit)])
async def list_audit_logs(
    admin_user: Annotated[User, Depends(require_roles("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
):
    """管理员查看最近审计日志。"""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return {
        "logs": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "action": log.action,
                "resource": log.resource,
                "detail": log.detail,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ]
    }


# ============================================================
# API: 会话管理
# ============================================================

@app.get("/api/sessions", response_model=dict, dependencies=[Depends(default_limit)])
async def list_sessions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """获取当前用户的所有会话列表"""
    stmt = select(DBSession).where(DBSession.user_id == current_user.id).order_by(DBSession.updated_at.desc())
    result = await db.execute(stmt)
    sessions = result.scalars().all()

    counts_stmt = (
        # 单独聚合消息数量，避免逐个会话查询造成 N+1。
        select(Message.session_id, func.count(Message.id))
        .where(Message.session_id.in_([s.id for s in sessions]))
        .group_by(Message.session_id)
    )
    counts_result = await db.execute(counts_stmt) if sessions else None
    message_counts = dict(counts_result.all()) if counts_result else {}

    return {
        "sessions": [
            SessionOut(
                session_id=s.id,
                title=s.title,
                question_type=s.question_type,
                message_count=message_counts.get(s.id, 0),
                updated_at=s.updated_at.isoformat() if s.updated_at else None,
            ) for s in sessions
        ]
    }


@app.delete("/api/session/{session_id}", dependencies=[Depends(default_limit)])
async def clear_session(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """清除指定会话（数据库 + FAISS 索引）"""
    stmt = select(DBSession).where(DBSession.id == session_id, DBSession.user_id == current_user.id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    await db.delete(session)
    await db.commit()

    agent.clear_memory(session_id)
    await write_audit_log(db, current_user.id, "session.delete", "session", session_id)
    return {"status": "ok"}


@app.get("/api/session/{session_id}", response_model=SessionDetail, dependencies=[Depends(default_limit)])
async def get_session(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=50),
):
    """获取指定会话消息（支持分页）"""
    # 验证会话归属
    stmt = select(DBSession).where(DBSession.id == session_id, DBSession.user_id == current_user.id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 获取消息总数
    count_stmt = select(func.count(Message.id)).where(Message.session_id == session_id)
    total = (await db.execute(count_stmt)).scalar() or 0

    # 获取分页消息
    # 先按时间倒序取最近 limit 条，再在响应里反转回正序，方便前端直接渲染。
    msg_stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    msg_result = await db.execute(msg_stmt)
    messages = msg_result.scalars().all()

    has_more = (offset + limit) < total

    return SessionDetail(
        session_id=session_id,
        messages=[
            MessageOut(role=m.role, content=m.content)
            for m in reversed(messages)  # 按时间正序返回
        ],
        has_more=has_more,
    )


# ============================================================
# API: 对话（核心）
# ============================================================

@app.post("/api/chat", dependencies=[Depends(chat_limit)])
async def chat(
    request: ChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """核心对话接口（SSE 流式响应，需认证）

    处理流程：
    1. 创建或获取会话（归属当前用户）
    2. 如有图片，OCR 提取文字 → 拼入消息
    3. 从数据库加载历史消息
    4. 流式调用 Agent.chat()
    5. 保存消息到数据库
    """
    session_id = request.session_id
    question_type = request.question_type

    # ----- 1. 创建或获取会话 -----
    if session_id:
        # 已有 session_id，验证归属
        stmt = select(DBSession).where(
            DBSession.id == session_id,
            DBSession.user_id == current_user.id,
        )
        result = await db.execute(stmt)
        db_session = result.scalar_one_or_none()
        if not db_session:
            raise HTTPException(status_code=404, detail="会话不存在")
    else:
        # 新建会话
        session_id = str(uuid.uuid4())
        db_session = DBSession(
            id=session_id,
            user_id=current_user.id,
            question_type=question_type or "free",
            title="新对话",
        )
        db.add(db_session)
        await db.commit()

    # ----- 2. 处理消息 -----
    user_message = request.message.strip()
    llm_message = user_message

    if request.images:
        all_texts = []
        for i, b64 in enumerate(request.images):
            text = ocr_image(b64)
            if text:
                text = _reformat_quiz_options(text)
                all_texts.append(f"[图{i + 1}]\n{text}")
        if all_texts:
            if question_type == "writing_b" and not user_message:
                # 大作文图表题没有补充说明时，引导模型先还原图表结构再生成写作分析。
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

    # ----- 3. 加载历史消息 -----
    msg_stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    msg_result = await db.execute(msg_stmt)
    db_messages = msg_result.scalars().all()
    history = [{"role": m.role, "content": m.content} for m in db_messages]

    # ----- 4. 保存用户消息到数据库 -----
    user_msg = Message(session_id=session_id, role="user", content=user_message or "(图片消息)")
    db.add(user_msg)
    await db.commit()

    # 首次对话：更新会话标题
    if not history:
        db_session.title = _fallback_title([{"role": "user", "content": user_message}])
        await db.commit()

    logger.info("对话请求：user=%d, session=%s, question_type=%s, msg_len=%d",
                current_user.id, session_id, question_type, len(llm_message))

    # ----- 5. 流式生成 -----
    async def generate():
        try:
            from backend.database import async_session_factory
        except ImportError:
            from database import async_session_factory

        yield f"data: {json.dumps({'session_id': session_id, 'content': '', 'done': False})}\n\n"

        full_response = ""
        async for chunk in agent.chat(
            session_id=session_id,
            message=llm_message,
            history=history,
            question_type=question_type,
        ):
            yield chunk

            if chunk.startswith("data: "):
                try:
                    # SSE chunk 可能包含思考态标记；这里只持久化真正展示给用户的正文。
                    data = json.loads(chunk[6:])
                    if data.get("content") and not data.get("thinking"):
                        full_response += data["content"]
                except (json.JSONDecodeError, KeyError):
                    pass

        # 保存 AI 回复（使用独立会话避免 generator 上下文问题）
        if full_response:
            try:
                async with async_session_factory() as save_db:
                    now = datetime.datetime.utcnow()
                    save_db.add(Message(
                        session_id=session_id,
                        role="assistant",
                        content=full_response,
                        created_at=now,
                    ))
                    # 更新会话时间
                    from sqlalchemy import update
                    await save_db.execute(
                        update(DBSession)
                        .where(DBSession.id == session_id)
                        .values(updated_at=now)
                    )
                    await save_db.commit()
            except Exception as e:
                logger.error("保存 AI 回复失败：%s", e)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


_mount_versioned_api_routes()


# ============================================================
# 生产模式：前端静态文件服务
# ============================================================

_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if _frontend_dist.exists():
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        file_path = _frontend_dist / (full_path or "index.html")
        if file_path.is_file():
            return FileResponse(file_path)
        index_path = _frontend_dist / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        raise HTTPException(status_code=404)


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("  考研英语二 AI 学习助手（企业版）")
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
