"""
限流模块 - Redis 优先、内存降级的请求频率限制

策略：
- 普通 API（/api/chat 除外）：100 次/分钟/IP
- 对话 API（/api/chat）：20 次/分钟/用户（需认证）
- 认证 API（/api/auth/*）：20 次/分钟/IP（防暴力破解）

降级：当 Redis 不可用时自动切换为内存模式（默认）
"""

import hashlib
import logging
import threading
import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, HTTPException, status
try:
    from redis.asyncio import Redis
    from redis.exceptions import RedisError
except ImportError:
    Redis = None

    class RedisError(Exception):
        pass

try:
    from .config import settings
except ImportError:
    from config import settings


# ============================================================
# 内存滑窗限流器
# ============================================================
logger = logging.getLogger(__name__)


class SlidingWindowLimiter:
    """基于滑窗的简单限流器，进程内存存储"""

    def __init__(self):
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, key: str, max_requests: int, window_seconds: float = 60.0) -> bool:
        """检查 key 是否在窗口内超过限流阈值"""
        now = time.time()
        with self._lock:
            window = self._windows[key]
            # 每次请求时顺手清理窗口外的旧时间戳，避免内存持续增长。
            cutoff = now - window_seconds
            while window and window[0] < cutoff:
                window.pop(0)
            # 清理后仍达到阈值，说明当前窗口内请求过多。
            if len(window) >= max_requests:
                return False
            window.append(now)
            return True

    def reset(self, key: str):
        with self._lock:
            self._windows.pop(key, None)


# 全局实例
_limiter = SlidingWindowLimiter()
_redis_client: Redis | None = None
_redis_ready = False

if settings.redis_url and Redis is not None:
    try:
        _redis_client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=settings.redis_socket_timeout_seconds,
            socket_connect_timeout=settings.redis_socket_timeout_seconds,
            max_connections=settings.redis_max_connections,
        )
        _redis_ready = True
        logger.info("Redis 限流已启用")
    except RedisError as exc:
        logger.warning("Redis 不可用，限流降级为内存模式：%s", exc)
        _redis_client = None
elif settings.redis_url:
    logger.warning("已配置 REDIS_URL，但未安装 redis 依赖，限流降级为内存模式")


async def _redis_is_allowed(key: str, max_requests: int, window_seconds: float) -> bool | None:
    """使用 Redis sorted set 实现跨进程滑窗限流；返回 None 表示降级。"""
    if _redis_client is None or not _redis_ready:
        return None
    now = time.time()
    redis_key = f"rate:{key}"
    try:
        pipe = _redis_client.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
        pipe.zcard(redis_key)
        pipe.zadd(redis_key, {f"{now}:{threading.get_ident()}": now})
        pipe.expire(redis_key, int(window_seconds) + 1)
        _, count, _, _ = await pipe.execute()
        return int(count) < max_requests
    except RedisError as exc:
        logger.warning("Redis 限流失败，降级为内存模式：%s", exc)
        return None


# ============================================================
# FastAPI 依赖
# ============================================================

def RateLimit(max_requests: int, window_seconds: float = 60.0, key_fn: Callable[[Request], str] | None = None):
    """限流依赖工厂

    Args:
        max_requests: 窗口内最大请求数
        window_seconds: 时间窗口（秒），默认 60
        key_fn: 生成限流 key 的函数，默认使用客户端 IP
    """
    async def limiter(request: Request):
        if key_fn:
            key = key_fn(request)
        else:
            # 默认：IP 限制
            forwarded = request.headers.get("X-Forwarded-For")
            ip = (forwarded or "").split(",")[0].strip() or (request.client.host if request.client else "unknown")
            key = f"{request.url.path}:{ip}"

        allowed = await _redis_is_allowed(key, max_requests, window_seconds)
        if allowed is None:
            allowed = _limiter.is_allowed(key, max_requests, window_seconds)

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求过于频繁，请等待 {window_seconds:.0f} 秒后重试",
            )

    return limiter


# ============================================================
# 预定义限流策略
# ============================================================

def _auth_or_ip_key(request: Request) -> str:
    """优先按 Authorization 区分用户；未登录请求退回到 IP 维度。"""
    auth = request.headers.get("Authorization", "")
    if auth:
        digest = hashlib.sha256(auth.encode("utf-8")).hexdigest()[:16]
        return f"{request.url.path}:auth:{digest}"
    forwarded = request.headers.get("X-Forwarded-For")
    ip = (forwarded or "").split(",")[0].strip() or (request.client.host if request.client else "unknown")
    return f"{request.url.path}:ip:{ip}"


# 普通 API（100次/分钟/IP）
default_limit = RateLimit(settings.default_rate_limit_per_minute)

# 对话 API（20次/分钟/用户）
chat_limit = RateLimit(settings.chat_rate_limit_per_minute, key_fn=_auth_or_ip_key)

# 认证 API（10次/分钟/IP，防爆破）
auth_limit = RateLimit(settings.auth_rate_limit_per_minute)
