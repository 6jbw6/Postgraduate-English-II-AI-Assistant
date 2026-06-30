"""
认证模块 - JWT 令牌生成/验证 + 密码哈希 + RBAC 权限依赖

端点：
- POST /api/auth/register  注册
- POST /api/auth/login     登录
- GET  /api/auth/me        获取当前用户信息

安全策略：
- 密码使用 bcrypt 哈希存储
- JWT 访问令牌有效期 24 小时
- 令牌存储在 Authorization: Bearer <token> 请求头
"""

import os
import datetime
from typing import Annotated, Callable
import re
import base64
import binascii

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from .database import AuditLog, get_db, User
    from .config import settings
except ImportError:
    from database import AuditLog, get_db, User
    from config import settings

# ============================================================
# 配置
# ============================================================
SECRET_KEY = settings.jwt_secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = settings.access_token_expire_hours
# 头像以 Data URL 存储时会比原始二进制膨胀约 1/3，因此字段长度和真实字节数分开校验。
AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_MAX_DATA_URL_CHARS = (AVATAR_MAX_BYTES * 4 // 3) + 1024

# HTTP Bearer 安全方案
security = HTTPBearer(auto_error=False)


# ============================================================
# Pydantic 模型
# ============================================================
class UserRegister(BaseModel):
    """注册请求体，负责基础格式规范化与校验。"""

    username: str = Field(min_length=2, max_length=64)
    email: str = Field(min_length=5, max_length=128)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        """限制用户名字符集，避免不可见字符或特殊符号影响展示与检索。"""
        value = value.strip()
        if not re.fullmatch(r"[\w\u4e00-\u9fff.-]+", value):
            raise ValueError("用户名仅支持中文、字母、数字、下划线、点和短横线")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """邮箱统一转小写，避免大小写造成重复账号。"""
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("邮箱格式不正确")
        return value


class UserLogin(BaseModel):
    """登录请求体。"""

    email: str = Field(min_length=5, max_length=128)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserOut(BaseModel):
    """返回给前端的用户信息，不包含密码哈希等敏感字段。"""

    id: int
    username: str
    email: str
    role: str = "student"
    display_name: str | None = None
    avatar_url: str | None = None
    exam_stage: str | None = None
    target_score: str | None = None
    study_goal: str | None = None

    model_config = {"from_attributes": True}


class UserProfileUpdate(BaseModel):
    """个人资料更新请求体。"""

    display_name: str | None = Field(default=None, max_length=64)
    avatar_url: str | None = Field(default=None, max_length=AVATAR_MAX_DATA_URL_CHARS)
    exam_stage: str | None = Field(default=None, max_length=64)
    target_score: str | None = Field(default=None, max_length=16)
    study_goal: str | None = Field(default=None, max_length=256)

    @field_validator("display_name", "avatar_url", "exam_stage", "target_score", "study_goal")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """把空字符串归一为 None，数据库中就不会保存无意义空值。"""
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("avatar_url")
    @classmethod
    def validate_avatar_url(cls, value: str | None) -> str | None:
        """头像允许远程图片或本地 Data URL；Data URL 需要校验真实图片字节大小。"""
        if value is None:
            return None
        if value.startswith("data:image/"):
            if "," not in value:
                raise ValueError("头像 Data URL 格式不正确")
            raw = value.split(",", 1)[1]
            try:
                decoded = base64.b64decode(raw, validate=True)
            except (binascii.Error, ValueError):
                raise ValueError("头像图片数据不是有效的 Base64")
            if len(decoded) > AVATAR_MAX_BYTES:
                raise ValueError("头像图片不能超过 2MB")
            return value
        if value.startswith("/uploads/") or value.startswith("https://") or value.startswith("http://"):
            return value
        raise ValueError("头像必须是图片 Data URL 或 http(s) 地址")


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ============================================================
# 密码工具（bcrypt 直接调用）
# ============================================================
def hash_password(password: str) -> str:
    """生成 bcrypt 密码哈希，数据库只保存哈希值。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码和数据库中的 bcrypt 哈希是否匹配。"""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ============================================================
# JWT 工具
# ============================================================
def create_access_token(user_id: int) -> str:
    """签发访问令牌，sub 字段固定存用户 ID。"""
    expire = datetime.datetime.utcnow() + datetime.timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> int | None:
    """解码 JWT，返回 user_id；无效则返回 None"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None


# ============================================================
# 认证依赖
# ============================================================
async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """从 Bearer Token 中解析当前用户；未认证则抛出 401"""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")

    user_id = decode_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录")

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")

    return user


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """可选的用户认证：有 Token 则解析，无则返回 None（不报错）"""
    if credentials is None:
        return None
    user_id = decode_token(credentials.credentials)
    if user_id is None:
        return None
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def require_roles(*roles: str) -> Callable[[User], User]:
    """RBAC 依赖工厂：限制接口只允许指定角色访问。"""
    allowed = set(roles)

    async def checker(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return current_user

    return checker


async def write_audit_log(
    db: AsyncSession,
    user_id: int | None,
    action: str,
    resource: str = "",
    detail: str = "",
) -> None:
    """写入审计日志；失败时不影响主业务事务。"""
    try:
        db.add(AuditLog(user_id=user_id, action=action, resource=resource, detail=detail))
        await db.commit()
    except Exception:
        await db.rollback()
