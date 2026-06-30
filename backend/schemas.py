"""
Pydantic 请求/响应模型

统一管理所有 API 的数据模型。
"""

import base64
import binascii

from pydantic import BaseModel, Field, field_validator

try:
    from .config import settings
except ImportError:
    from config import settings


# ---- 对话 ----
class ChatRequest(BaseModel):
    """聊天接口请求体，负责限制文本长度、图片数量和图片体积。"""

    session_id: str = Field(default="", max_length=64)
    message: str = Field(default="", max_length=settings.max_message_chars)
    question_type: str | None = Field(default=None, max_length=32)
    images: list[str] | None = Field(default=None, max_length=settings.max_images_per_request)

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        """去掉首尾空白，避免空格消息进入业务逻辑。"""
        return value.strip()

    @field_validator("images")
    @classmethod
    def validate_images(cls, value: list[str] | None) -> list[str] | None:
        """校验前端传来的 Base64 图片，支持纯 Base64 和完整 Data URL。"""
        if not value:
            return value
        for item in value:
            raw = item.split(",", 1)[1] if item.startswith("data:") and "," in item else item
            try:
                decoded = base64.b64decode(raw, validate=True)
            except (binascii.Error, ValueError):
                raise ValueError("图片数据不是有效的 Base64")
            if len(decoded) > settings.max_image_bytes:
                max_mb = settings.max_image_bytes // (1024 * 1024)
                raise ValueError(f"单张图片不能超过 {max_mb} MB")
        return value


# ---- 会话 ----
class SessionOut(BaseModel):
    """会话列表项，用于侧边栏/首页展示最近会话。"""

    session_id: str
    title: str
    question_type: str | None = None
    message_count: int
    updated_at: str | None = None


class MessageOut(BaseModel):
    """单条历史消息。"""

    role: str
    content: str

    model_config = {"from_attributes": True}


class SessionDetail(BaseModel):
    """分页历史消息响应。"""

    session_id: str
    messages: list[MessageOut]
    has_more: bool
