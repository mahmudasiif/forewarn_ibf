"""Object-storage helper for the worker (MinIO / S3), reading S3_* from env."""
from __future__ import annotations

import os
from functools import lru_cache

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

BUCKET = os.getenv("S3_BUCKET", "forewarn")


@lru_cache
def get_s3():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT_URL", "http://minio:9000"),
        aws_access_key_id=os.getenv("S3_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY", "minioadmin"),
        region_name=os.getenv("S3_REGION", "us-east-1"),
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket() -> None:
    s3 = get_s3()
    try:
        s3.head_bucket(Bucket=BUCKET)
    except ClientError:
        s3.create_bucket(Bucket=BUCKET)


def download_file(key: str, dest: str) -> None:
    get_s3().download_file(BUCKET, key, dest)


def put_file(key: str, path: str, content_type: str | None = None) -> str:
    ensure_bucket()
    extra = {"ContentType": content_type} if content_type else None
    get_s3().upload_file(path, BUCKET, key, ExtraArgs=extra)
    return key
