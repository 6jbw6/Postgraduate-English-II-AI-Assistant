"""
生产硬化中间件

职责：
- 生成/透传请求 ID，便于排查跨服务调用。
- 记录访问日志和耗时。
- 设置基础安全响应头。
- 在进入业务逻辑前限制请求体大小。
"""

from __future__ import annotations

import json
import logging
import time
import uuid

from fastapi import Request
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

try:
    from .config import settings
except ImportError:
    from config import settings


logger = logging.getLogger("app.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """为每个请求补充上下文、安全头和访问日志。"""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start = time.perf_counter()
        request.state.request_id = request_id

        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.max_request_bytes:
            response = JSONResponse(
                status_code=413,
                content={"detail": "请求体过大"},
            )
        else:
            try:
                response = await call_next(request)
            except Exception:
                self._log_access(request, request_id, start, 500)
                raise

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = f"{duration_ms:.2f}"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self._log_access(request, request_id, start, response.status_code)
        return response

    def _log_access(self, request: Request, request_id: str, start: float, status_code: int) -> None:
        """记录结构化访问日志；生产环境可开启 JSON_LOGS 便于日志平台采集。"""
        if not settings.access_log_enabled:
            return

        duration_ms = (time.perf_counter() - start) * 1000
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if not client_ip and request.client:
            client_ip = request.client.host

        event = {
            "event": "http_request",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "client_ip": client_ip or "unknown",
        }
        if settings.json_logs:
            logger.info(json.dumps(event, ensure_ascii=False))
        else:
            logger.info(
                "%s %s status=%s duration_ms=%.2f request_id=%s client_ip=%s",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
                request_id,
                client_ip or "unknown",
            )
