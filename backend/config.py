"""
运行时配置中心

配置优先从环境变量读取；本地开发时会轻量加载项目根目录下的 .env。
生产环境应通过部署平台注入密钥，避免把敏感信息写进镜像或代码仓库。
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
MEMORY_DIR = ROOT_DIR / "memory"


def _load_dotenv() -> None:
    """加载本地 .env，但不覆盖已经存在的环境变量。"""
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _csv(value: str | None, default: list[str]) -> list[str]:
    """把逗号分隔的环境变量解析成列表。"""
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _bool(name: str, default: bool) -> bool:
    """兼容常见布尔环境变量写法，如 true/yes/on/1。"""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    """解析整数环境变量；非法输入回退默认值，避免启动直接崩溃。"""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    """解析浮点环境变量；非法输入回退默认值。"""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


_load_dotenv()


class Settings(BaseModel):
    """应用所有可配置项的单一入口。"""
    app_name: str = "考研英语二 AI 学习助手"
    app_version: str = "2.1.0"
    app_env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    json_logs: bool = Field(default_factory=lambda: _bool("JSON_LOGS", False))
    access_log_enabled: bool = Field(default_factory=lambda: _bool("ACCESS_LOG_ENABLED", True))
    max_request_bytes: int = Field(
        default_factory=lambda: _int("MAX_REQUEST_BYTES", 12 * 1024 * 1024),
        ge=1024,
    )

    database_url: str = Field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "mysql+aiomysql://english_user:english_password@localhost:3306/english_ii?charset=utf8mb4",
        )
    )
    db_pool_size: int = Field(default_factory=lambda: _int("DB_POOL_SIZE", 10), ge=1)
    db_max_overflow: int = Field(default_factory=lambda: _int("DB_MAX_OVERFLOW", 20), ge=0)
    db_pool_timeout_seconds: int = Field(default_factory=lambda: _int("DB_POOL_TIMEOUT_SECONDS", 30), ge=1)
    db_pool_recycle_seconds: int = Field(default_factory=lambda: _int("DB_POOL_RECYCLE_SECONDS", 1800), ge=1)
    sqlite_busy_timeout_seconds: int = Field(default_factory=lambda: _int("SQLITE_BUSY_TIMEOUT_SECONDS", 30), ge=1)

    jwt_secret_key: str = Field(
        default_factory=lambda: os.getenv(
            "JWT_SECRET_KEY",
            "dev-only-change-me-please-32-characters-min",
        )
    )
    access_token_expire_hours: int = Field(
        default_factory=lambda: _int("ACCESS_TOKEN_EXPIRE_HOURS", 24),
        ge=1,
        le=24 * 30,
    )
    admin_emails: list[str] = Field(
        default_factory=lambda: _csv(os.getenv("ADMIN_EMAILS"), [])
    )

    cors_origins: list[str] = Field(
        default_factory=lambda: _csv(
            os.getenv("CORS_ORIGINS"),
            ["http://localhost:5173", "http://127.0.0.1:5173"],
        )
    )
    cors_allow_credentials: bool = Field(
        default_factory=lambda: _bool("CORS_ALLOW_CREDENTIALS", True)
    )

    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_base_url: str = Field(
        default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    )
    openai_model: str = Field(default_factory=lambda: os.getenv("OPENAI_MODEL", "deepseek-chat"))
    openai_embedding_model: str = Field(
        default_factory=lambda: os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    )
    openai_timeout_seconds: float = Field(
        default_factory=lambda: _float("OPENAI_TIMEOUT_SECONDS", 120.0),
        gt=0,
    )
    llm_max_concurrency: int = Field(default_factory=lambda: _int("LLM_MAX_CONCURRENCY", 8), ge=1)
    chat_history_messages_limit: int = Field(
        default_factory=lambda: _int("CHAT_HISTORY_MESSAGES_LIMIT", 20),
        ge=2,
    )

    ocr_enabled: bool = Field(default_factory=lambda: _bool("OCR_ENABLED", True))
    ocr_max_concurrency: int = Field(default_factory=lambda: _int("OCR_MAX_CONCURRENCY", 2), ge=1)
    memory_dir: Path = Field(default_factory=lambda: Path(os.getenv("MEMORY_DIR", str(MEMORY_DIR))))
    max_images_per_request: int = Field(default_factory=lambda: _int("MAX_IMAGES_PER_REQUEST", 9), ge=0, le=20)
    max_image_bytes: int = Field(default_factory=lambda: _int("MAX_IMAGE_BYTES", 8 * 1024 * 1024), ge=1024)
    max_message_chars: int = Field(default_factory=lambda: _int("MAX_MESSAGE_CHARS", 20000), ge=1)

    default_rate_limit_per_minute: int = Field(
        default_factory=lambda: _int("DEFAULT_RATE_LIMIT_PER_MINUTE", 100),
        ge=1,
    )
    chat_rate_limit_per_minute: int = Field(
        default_factory=lambda: _int("CHAT_RATE_LIMIT_PER_MINUTE", 20),
        ge=1,
    )
    auth_rate_limit_per_minute: int = Field(
        default_factory=lambda: _int("AUTH_RATE_LIMIT_PER_MINUTE", 10),
        ge=1,
    )

    redis_url: str = Field(default_factory=lambda: os.getenv("REDIS_URL", ""))
    redis_socket_timeout_seconds: float = Field(
        default_factory=lambda: _float("REDIS_SOCKET_TIMEOUT_SECONDS", 1.0),
        gt=0,
    )
    redis_max_connections: int = Field(default_factory=lambda: _int("REDIS_MAX_CONNECTIONS", 50), ge=1)
    cache_default_ttl_seconds: int = Field(
        default_factory=lambda: _int("CACHE_DEFAULT_TTL_SECONDS", 300),
        ge=1,
    )

    storage_backend: str = Field(default_factory=lambda: os.getenv("STORAGE_BACKEND", "local"))
    storage_local_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("STORAGE_LOCAL_DIR", str(DATA_DIR / "uploads")))
    )
    storage_base_url: str = Field(default_factory=lambda: os.getenv("STORAGE_BASE_URL", ""))
    s3_endpoint_url: str = Field(default_factory=lambda: os.getenv("S3_ENDPOINT_URL", ""))
    s3_bucket: str = Field(default_factory=lambda: os.getenv("S3_BUCKET", ""))
    s3_region: str = Field(default_factory=lambda: os.getenv("S3_REGION", "us-east-1"))
    s3_access_key_id: str = Field(default_factory=lambda: os.getenv("S3_ACCESS_KEY_ID", ""))
    s3_secret_access_key: str = Field(default_factory=lambda: os.getenv("S3_SECRET_ACCESS_KEY", ""))

    @property
    def is_production(self) -> bool:
        """判断是否运行在生产环境，用于启用更严格的安全校验。"""
        return self.app_env.lower() in {"prod", "production"}

    @property
    def sync_database_url(self) -> str:
        """把异步数据库 URL 转成同步 URL，供建表/迁移等同步 API 使用。"""
        if self.database_url.startswith("sqlite+aiosqlite:///"):
            return self.database_url.replace("sqlite+aiosqlite:///", "sqlite:///", 1)
        if self.database_url.startswith("postgresql+asyncpg://"):
            return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        if self.database_url.startswith("mysql+aiomysql://"):
            return self.database_url.replace("mysql+aiomysql://", "mysql+pymysql://", 1)
        return self.database_url

    @model_validator(mode="after")
    def validate_security_defaults(self) -> "Settings":
        """集中兜底危险配置，避免生产环境带着开发默认值运行。"""
        if "*" in self.cors_origins and self.cors_allow_credentials:
            logging.getLogger(__name__).warning(
                "CORS_ORIGINS contains '*'; disabling credentialed CORS responses."
            )
            self.cors_allow_credentials = False

        using_dev_secret = self.jwt_secret_key.startswith("dev-only-change-me")
        if self.is_production and using_dev_secret:
            raise RuntimeError("JWT_SECRET_KEY must be configured for production deployments.")
        if self.is_production and len(self.jwt_secret_key) < 32:
            raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    """缓存配置对象，确保全应用共享同一份设置。"""
    settings = Settings()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings.memory_dir.mkdir(parents=True, exist_ok=True)
    settings.storage_local_dir.mkdir(parents=True, exist_ok=True)
    return settings


settings = get_settings()
