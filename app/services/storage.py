"""Private object storage with local-development and S3-compatible backends."""

import asyncio
from pathlib import Path
from uuid import uuid4

from app.core.config import settings


class StorageError(RuntimeError):
    pass


def object_key(user_id: int, category: str, suffix: str) -> str:
    safe_suffix = suffix.lower().lstrip(".")[:12]
    return f"users/{user_id}/{category}/{uuid4()}.{safe_suffix}"


class ObjectStorage:
    def __init__(self) -> None:
        self.backend = settings.storage_backend
        self.root = Path(settings.storage_local_path).resolve()

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        if self.backend == "local":
            await asyncio.to_thread(self._local_put, key, data)
            return
        await asyncio.to_thread(self._s3_put, key, data, content_type)

    async def get(self, key: str) -> bytes:
        if self.backend == "local":
            return await asyncio.to_thread(self._local_get, key)
        return await asyncio.to_thread(self._s3_get, key)

    async def delete(self, key: str | None) -> None:
        if not key:
            return
        if self.backend == "local":
            await asyncio.to_thread(self._local_delete, key)
            return
        await asyncio.to_thread(self._s3_delete, key)

    def _local_path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise StorageError("Invalid storage key")
        return path

    def _local_put(self, key: str, data: bytes) -> None:
        path = self._local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)

    def _local_get(self, key: str) -> bytes:
        try:
            return self._local_path(key).read_bytes()
        except OSError as exc:
            raise StorageError("Stored object is unavailable") from exc

    def _local_delete(self, key: str) -> None:
        try:
            self._local_path(key).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("Stored object could not be deleted") from exc

    def _s3_client(self):
        try:
            import boto3
        except ImportError as exc:
            raise StorageError("boto3 is required for S3 object storage") from exc
        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key or None,
            aws_secret_access_key=settings.s3_secret_key or None,
            region_name=settings.s3_region,
        )
        try:
            client.head_bucket(Bucket=settings.s3_bucket)
        except Exception:
            client.create_bucket(Bucket=settings.s3_bucket)
        return client

    def _s3_put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self._s3_client().put_object(
                Bucket=settings.s3_bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except Exception as exc:
            raise StorageError("Object upload failed") from exc

    def _s3_get(self, key: str) -> bytes:
        try:
            response = self._s3_client().get_object(Bucket=settings.s3_bucket, Key=key)
            return response["Body"].read()
        except Exception as exc:
            raise StorageError("Stored object is unavailable") from exc

    def _s3_delete(self, key: str) -> None:
        try:
            self._s3_client().delete_object(Bucket=settings.s3_bucket, Key=key)
        except Exception as exc:
            raise StorageError("Stored object could not be deleted") from exc


storage = ObjectStorage()
