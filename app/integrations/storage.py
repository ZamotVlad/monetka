"""Where statement files live: S3 in production, LocalStack locally, a dict in tests."""

import logging
from typing import Any, Protocol

import aioboto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings

logger = logging.getLogger(__name__)


class FileStorage(Protocol):
    async def put(self, key: str, body: bytes, content_type: str) -> None: ...

    async def download_url(self, key: str, expires_seconds: int = 900) -> str: ...


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session = aioboto3.Session(
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )

    async def ensure_bucket(self) -> None:
        try:
            async with self._client(self._settings.s3_endpoint_url) as s3:
                await s3.create_bucket(
                    Bucket=self._settings.s3_bucket,
                    CreateBucketConfiguration={"LocationConstraint": self._settings.aws_region},
                )
        except ClientError as error:
            if error.response["Error"]["Code"] != "BucketAlreadyOwnedByYou":
                raise
        except BotoCoreError as error:
            logger.warning("object storage unavailable: %s", error)

    async def put(self, key: str, body: bytes, content_type: str) -> None:
        async with self._client(self._settings.s3_endpoint_url) as s3:
            await s3.put_object(
                Bucket=self._settings.s3_bucket, Key=key, Body=body, ContentType=content_type
            )

    async def download_url(self, key: str, expires_seconds: int = 900) -> str:
        # Signed for the address the browser sees, which in Docker differs from ours
        async with self._client(self._settings.s3_public_endpoint_url) as s3:
            url: str = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._settings.s3_bucket, "Key": key},
                ExpiresIn=expires_seconds,
            )
            return url

    def _client(self, endpoint_url: str | None) -> Any:
        return self._session.client("s3", endpoint_url=endpoint_url)


class MemoryStorage:
    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, body: bytes, content_type: str) -> None:
        self.files[key] = (body, content_type)

    async def download_url(self, key: str, expires_seconds: int = 900) -> str:
        return f"memory://{key}"
