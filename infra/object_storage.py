"""MinIO 对象存储封装。"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import BinaryIO

try:
    from minio import Minio
except ImportError:
    Minio = None  # type: ignore[misc, assignment]


class ObjectStorage:
    def __init__(self) -> None:
        self._client = None
        self.mode = "fallback"
        if Minio is not None:
            endpoint = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
            access = os.environ.get("MINIO_USER", "minioadmin")
            secret = os.environ.get("MINIO_PASSWORD", "minioadmin")
            secure = os.environ.get("MINIO_SECURE", "0") in ("1", "true", "yes")
            try:
                self._client = Minio(endpoint, access_key=access, secret_key=secret, secure=secure)
                self.mode = "minio"
            except Exception:
                self._client = None
        self._fallback_dir = Path(os.environ.get("VIDEO_OUTPUT_DIR", "data/output/videos"))
        self._fallback_dir.mkdir(parents=True, exist_ok=True)

    def ping(self) -> bool:
        if self._client is None:
            return False
        try:
            self._client.list_buckets()
            return True
        except Exception:
            return False

    def upload(self, bucket: str, object_name: str, file_path: str, content_type: str = "video/mp4") -> str:
        if self._client is not None:
            if not self._client.bucket_exists(bucket):
                self._client.make_bucket(bucket)
            self._client.fput_object(bucket, object_name, file_path, content_type=content_type)
            return f"{bucket}/{object_name}"
        dest = self._fallback_dir / object_name
        dest.write_bytes(Path(file_path).read_bytes())
        return str(dest)

    def upload_stream(self, bucket: str, object_name: str, data: BinaryIO, length: int) -> str:
        if self._client is not None:
            if not self._client.bucket_exists(bucket):
                self._client.make_bucket(bucket)
            self._client.put_object(bucket, object_name, data, length)
            return f"{bucket}/{object_name}"
        dest = self._fallback_dir / object_name
        dest.write_bytes(data.read())
        return str(dest)

    def upload_bytes(self, bucket: str, object_name: str, payload: bytes, content_type: str = "application/octet-stream") -> str:
        return self.upload_stream(bucket, object_name, io.BytesIO(payload), len(payload))
