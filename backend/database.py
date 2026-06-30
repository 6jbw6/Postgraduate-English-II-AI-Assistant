"""
数据库模块 - SQLAlchemy 异步引擎 + ORM 模型

替代原有的 sessions.json + pickle 文件持久化方案。
默认使用 MySQL；也兼容 SQLite（开发/单机）或 PostgreSQL 等 SQLAlchemy 支持的数据库。

表结构：
- users:     用户表（id, username, email, password_hash, created_at）
- sessions:  会话表（id, user_id, question_type, title, created_at, updated_at）
- messages:  消息表（id, session_id, role, content, created_at）
- audit_logs: 审计日志表（id, user_id, action, resource, detail, created_at）
"""

import datetime
from pathlib import Path

from sqlalchemy import (
    Column, String, Text, DateTime, Integer, ForeignKey, create_engine, event, inspect, text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

try:
    from .config import settings
except ImportError:
    from config import settings

# ============================================================
# 配置
# ============================================================
_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"
_DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = settings.database_url
# 同步 URL（用于创建表等操作）
SYNC_DATABASE_URL = settings.sync_database_url

_ASYNC_ENGINE_OPTIONS = {"echo": False, "future": True}
_SYNC_ENGINE_OPTIONS = {"echo": False}

if not DATABASE_URL.startswith("sqlite"):
    _ASYNC_ENGINE_OPTIONS.update({
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout_seconds,
        "pool_recycle": settings.db_pool_recycle_seconds,
        "pool_pre_ping": True,
    })

if not SYNC_DATABASE_URL.startswith("sqlite"):
    _SYNC_ENGINE_OPTIONS.update({
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout_seconds,
        "pool_recycle": settings.db_pool_recycle_seconds,
        "pool_pre_ping": True,
    })

# 异步引擎
engine = create_async_engine(DATABASE_URL, **_ASYNC_ENGINE_OPTIONS)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# 同步引擎（仅用于 create_all）
sync_engine = create_engine(SYNC_DATABASE_URL, **_SYNC_ENGINE_OPTIONS)


def _enable_sqlite_wal(dbapi_connection, connection_record):
    """启用 SQLite WAL 和忙等待，提升单机并发写入稳定性。"""
    import sqlite3
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.execute("PRAGMA journal_mode=WAL")
        dbapi_connection.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_seconds * 1000}")
        dbapi_connection.execute("PRAGMA synchronous=NORMAL")


event.listen(sync_engine, "connect", _enable_sqlite_wal)
event.listen(engine.sync_engine, "connect", _enable_sqlite_wal)


# ============================================================
# Base
# ============================================================
class Base(DeclarativeBase):
    pass


# ============================================================
# ORM 模型
# ============================================================

class User(Base):
    """用户表：保存登录凭据与个人资料。"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(32), default="student", nullable=False)
    display_name = Column(String(64), nullable=True)
    avatar_url = Column(Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=True)
    exam_stage = Column(String(64), nullable=True)
    target_score = Column(String(16), nullable=True)
    study_goal = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # 删除用户时同步删除其会话，避免残留孤儿数据。
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")


class Session(Base):
    """会话表：一个用户在某个题型下的一段连续对话。"""

    __tablename__ = "sessions"

    id = Column(String(64), primary_key=True)  # UUID
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question_type = Column(String(32), default="free")
    title = Column(String(128), default="新对话")
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="sessions")
    # 会话删除时同步删除消息；默认按创建时间正序读取，便于构建 LLM 历史上下文。
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan",
                            order_by="Message.created_at")


class Message(Base):
    """消息表：保存用户和助手的文本消息。"""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(16), nullable=False)  # "user" | "assistant"
    content = Column(Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=False, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    session = relationship("Session", back_populates="messages")


class AuditLog(Base):
    """审计日志表：记录关键安全/数据操作，便于企业环境追踪。"""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(64), nullable=False)
    resource = Column(String(128), nullable=False, default="")
    detail = Column(Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=False, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)


# ============================================================
# 初始化
# ============================================================
def init_db():
    """创建所有表（同步调用，在应用启动时执行一次）"""
    Base.metadata.create_all(sync_engine)
    _ensure_user_profile_columns()


def _ensure_user_profile_columns():
    """为已有 SQLite 数据库补齐个人资料字段。

    正式生产建议使用 Alembic 管理迁移；这里保持单机部署开箱可升级。
    """
    if not SYNC_DATABASE_URL.startswith("sqlite:"):
        return

    columns = {column["name"] for column in inspect(sync_engine).get_columns("users")}
    profile_columns = {
        "role": "VARCHAR(32) NOT NULL DEFAULT 'student'",
        "display_name": "VARCHAR(64)",
        "avatar_url": "TEXT",
        "exam_stage": "VARCHAR(64)",
        "target_score": "VARCHAR(16)",
        "study_goal": "VARCHAR(256)",
    }

    with sync_engine.begin() as conn:
        for name, column_type in profile_columns.items():
            if name not in columns:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {column_type}"))


# ============================================================
# 依赖注入
# ============================================================
async def get_db() -> AsyncSession:
    """FastAPI 依赖：获取异步数据库会话"""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            # FastAPI 依赖退出时主动关闭连接，避免长时间占用连接池。
            await session.close()
