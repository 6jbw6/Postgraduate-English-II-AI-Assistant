"""
缓存抽象层

当前优先使用 Redis；未配置或不可用时自动降级为空实现。
业务代码可以安全调用，不需要到处判断 Redis 是否存在。
"""

from __future__ import annotations

import json
import logging
from typing import Any

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


logger = logging.getLogger(__name__)
_redis: Redis | None = None

if settings.redis_url and Redis is not None:
    try:
        _redis = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=settings.redis_socket_timeout_seconds,
            socket_connect_timeout=settings.redis_socket_timeout_seconds,
            max_connections=settings.redis_max_connections,
        )
        logger.info("Redis 缓存已启用")
    except RedisError as exc:
        logger.warning("Redis 缓存不可用，降级为空缓存：%s", exc)
        _redis = None
elif settings.redis_url:
    logger.warning("已配置 REDIS_URL，但未安装 redis 依赖，缓存降级为空实现")


def make_cache_key(namespace: str, key: str) -> str:
    """生成统一缓存 key，避免不同业务互相覆盖。"""
    return f"cache:{namespace}:{key}"


async def cache_get(namespace: str, key: str) -> Any | None:
    """读取 JSON 缓存；缓存缺失或 Redis 不可用时返回 None。"""
    if _redis is None:
        return None
    try:
        raw = await _redis.get(make_cache_key(namespace, key))
        return json.loads(raw) if raw else None
    except (RedisError, json.JSONDecodeError) as exc:
        logger.warning("读取缓存失败：%s", exc)
        return None


async def cache_set(namespace: str, key: str, value: Any, ttl_seconds: int | None = None) -> None:
    """写入 JSON 缓存。"""
    if _redis is None:
        return
    ttl = ttl_seconds or settings.cache_default_ttl_seconds
    try:
        await _redis.setex(make_cache_key(namespace, key), ttl, json.dumps(value, ensure_ascii=False))
    except (RedisError, TypeError) as exc:
        logger.warning("写入缓存失败：%s", exc)


async def cache_delete(namespace: str, key: str) -> None:
    """删除指定缓存。"""
    if _redis is None:
        return
    try:
        await _redis.delete(make_cache_key(namespace, key))
    except RedisError as exc:
        logger.warning("删除缓存失败：%s", exc)
