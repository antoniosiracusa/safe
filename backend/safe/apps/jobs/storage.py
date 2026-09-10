"""Object storage per i risultati dei job (MinIO in sviluppo, S3 compatibile in produzione).
Le chiavi sono per società: {company_id}/{kind}/{job_id}.{ext}. Nessun dato personale nei nomi."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from django.conf import settings

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket() -> None:
    c = client()
    try:
        c.head_bucket(Bucket=settings.S3_BUCKET)
    except ClientError:
        c.create_bucket(Bucket=settings.S3_BUCKET)


def put(key: str, data: bytes, content_type: str) -> None:
    ensure_bucket()
    client().put_object(Bucket=settings.S3_BUCKET, Key=key, Body=data, ContentType=content_type)


def get(key: str) -> bytes:
    obj = client().get_object(Bucket=settings.S3_BUCKET, Key=key)
    return obj["Body"].read()


def exists(key: str) -> bool:
    try:
        client().head_object(Bucket=settings.S3_BUCKET, Key=key)
        return True
    except ClientError:
        return False


def delete(key: str) -> None:
    try:
        client().delete_object(Bucket=settings.S3_BUCKET, Key=key)
    except ClientError as exc:  # pragma: no cover
        log.warning("delete %s fallita: %s", key, exc)
