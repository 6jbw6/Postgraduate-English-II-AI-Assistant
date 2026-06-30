"""
对象存储抽象

默认使用本地磁盘保存上传文件；生产环境可通过 S3 兼容服务（如 MinIO、AWS S3）
保存头像等二进制对象，数据库只保存可访问 URL。
"""

from __future__ import annotations

import base64
import binascii
import mimetypes
import uuid
import asyncio
from dataclasses import dataclass
from pathlib import Path

try:
    import boto3
except ImportError:
    boto3 = None

try:
    from .config import settings
except ImportError:
    from config import settings


@dataclass
class StoredObject:
    url: str
    key: str


def decode_data_url(data_url: str) -> tuple[bytes, str]:
    """解析 Data URL，返回二进制内容和 MIME 类型。"""
    if not data_url.startswith("data:") or "," not in data_url:
        raise ValueError("Data URL 格式不正确")
    header, raw = data_url.split(",", 1)
    mime_type = header.removeprefix("data:").split(";", 1)[0] or "application/octet-stream"
    try:
        return base64.b64decode(raw, validate=True), mime_type
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Data URL 内容不是有效的 Base64") from exc


def _extension_for_mime(mime_type: str) -> str:
    """根据 MIME 类型推断文件扩展名。"""
    return mimetypes.guess_extension(mime_type) or ".bin"


class ObjectStorage:
    """统一对象存储入口。"""

    def __init__(self) -> None:
        self.backend = settings.storage_backend.lower()

    def save_bytes(self, content: bytes, mime_type: str, prefix: str = "uploads") -> StoredObject:
        """保存二进制对象并返回访问 URL。"""
        ext = _extension_for_mime(mime_type)
        key = f"{prefix}/{uuid.uuid4().hex}{ext}"
        if self.backend == "s3":
            return self._save_s3(key, content, mime_type)
        return self._save_local(key, content)

    async def save_bytes_async(self, content: bytes, mime_type: str, prefix: str = "uploads") -> StoredObject:
        """异步保存对象，内部用线程池隔离文件系统/S3 阻塞调用。"""
        return await asyncio.to_thread(self.save_bytes, content, mime_type, prefix)

    def _save_local(self, key: str, content: bytes) -> StoredObject:
        target = settings.storage_local_dir / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        base = settings.storage_base_url.rstrip("/")
        url = f"{base}/uploads/{key}" if base else f"/uploads/{key}"
        return StoredObject(url=url, key=key)

    def _save_s3(self, key: str, content: bytes, mime_type: str) -> StoredObject:
        if boto3 is None:
            raise RuntimeError("STORAGE_BACKEND=s3 需要安装 boto3 依赖")
        if not settings.s3_bucket:
            raise RuntimeError("S3_BUCKET 未配置")
        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id or None,
            aws_secret_access_key=settings.s3_secret_access_key or None,
        )
        client.put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=content,
            ContentType=mime_type,
        )
        base = settings.storage_base_url.rstrip("/")
        url = f"{base}/{key}" if base else f"s3://{settings.s3_bucket}/{key}"
        return StoredObject(url=url, key=key)


storage = ObjectStorage()
