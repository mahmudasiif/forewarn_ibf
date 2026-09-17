"""Object-storage helper (MinIO / S3).

The portal keeps large, durable artifacts in object storage rather than in the
database or on a container's local disk. Model runs write their maps and
spreadsheets here; the API streams them back on download. Reads the S3_* settings
from core.config — nothing else in the app talks to boto3 directly.
"""
from __future__ import annotations

from functools import lru_cache
from typing import IO

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings


@lru_cache
def get_s3():
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket() -> None:
    """Create the configured bucket if it does not exist. Idempotent."""
    s3 = get_s3()
    try:
        s3.head_bucket(Bucket=settings.S3_BUCKET)
    except ClientError:
        s3.create_bucket(Bucket=settings.S3_BUCKET)


def put_file(key: str, path: str, content_type: str | None = None) -> str:
    """Upload a local file to object storage; return the object key."""
    ensure_bucket()
    extra = {"ContentType": content_type} if content_type else None
    get_s3().upload_file(path, settings.S3_BUCKET, key, ExtraArgs=extra)
    return key


def put_fileobj(key: str, fileobj: IO[bytes], content_type: str | None = None) -> str:
    """Upload from an open binary stream (e.g. an upload) to object storage."""
    ensure_bucket()
    extra = {"ContentType": content_type} if content_type else None
    get_s3().upload_fileobj(fileobj, settings.S3_BUCKET, key, ExtraArgs=extra)
    return key


def open_stream(key: str) -> IO[bytes]:
    """Return a streaming body for an object (raises if missing)."""
    obj = get_s3().get_object(Bucket=settings.S3_BUCKET, Key=key)
    return obj["Body"]


def object_exists(key: str) -> bool:
    try:
        get_s3().head_object(Bucket=settings.S3_BUCKET, Key=key)
        return True
    except ClientError:
        return False
