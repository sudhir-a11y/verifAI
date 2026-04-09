from __future__ import annotations

from urllib.parse import quote

import boto3
import httpx
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings


class StorageConfigError(Exception):
    pass


class StorageOperationError(Exception):
    pass


def _s3_client():
    kwargs = {"region_name": settings.s3_region}
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url

    if settings.s3_access_key and settings.s3_secret_key:
        kwargs["aws_access_key_id"] = settings.s3_access_key
        kwargs["aws_secret_access_key"] = settings.s3_secret_key

    return boto3.client("s3", **kwargs)


def _resolve_bucket(bucket: str | None) -> str:
    resolved = str(bucket or settings.s3_bucket or "").strip()
    if not resolved:
        raise StorageConfigError("S3 bucket is not configured")
    return resolved


def _public_object_url(bucket: str, key: str) -> str:
    escaped_key = quote(key, safe="/-_.~")
    if settings.s3_endpoint_url:
        endpoint = settings.s3_endpoint_url.rstrip("/")
        return f"{endpoint}/{bucket}/{escaped_key}"
    return f"https://{bucket}.s3.{settings.s3_region}.amazonaws.com/{escaped_key}"


def upload_bytes(object_key: str, payload: bytes, content_type: str) -> dict:
    client = _s3_client()
    bucket = _resolve_bucket(None)
    try:
        response = client.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=payload,
            ContentType=content_type,
        )
    except (ClientError, BotoCoreError) as exc:
        raise StorageOperationError(f"S3 upload failed: {exc}") from exc

    return {
        "bucket": bucket,
        "region": settings.s3_region,
        "key": object_key,
        "url": _public_object_url(bucket, object_key),
        "etag": response.get("ETag", "").strip('"'),
    }


def generate_download_url(object_key: str, expires_in: int = 900, *, bucket: str | None = None) -> str:
    client = _s3_client()
    resolved_bucket = _resolve_bucket(bucket)
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": resolved_bucket, "Key": object_key},
            ExpiresIn=expires_in,
        )
    except (ClientError, BotoCoreError) as exc:
        raise StorageOperationError(f"S3 presign failed: {exc}") from exc


def download_http_bytes(url: str, *, timeout_s: float = 60.0) -> bytes:
    safe_url = str(url or "").strip()
    if not safe_url.startswith(("http://", "https://")):
        raise StorageOperationError("HTTP download requires http(s) URL")
    try:
        with httpx.Client(timeout=float(timeout_s or 60.0), follow_redirects=True) as client:
            resp = client.get(safe_url, headers={"User-Agent": "verifAI/1.0"})
        resp.raise_for_status()
        return resp.content
    except httpx.HTTPStatusError as exc:
        status = getattr(exc.response, "status_code", None)
        raise StorageOperationError(f"HTTP download failed (status={status})") from exc
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise StorageOperationError(f"HTTP download failed: {exc}") from exc


def download_bytes(object_key: str, *, bucket: str | None = None) -> bytes:
    client = _s3_client()
    resolved_bucket = _resolve_bucket(bucket)
    try:
        response = client.get_object(Bucket=resolved_bucket, Key=object_key)
        body = response["Body"].read()
        return body
    except (ClientError, BotoCoreError) as exc:
        raise StorageOperationError(f"S3 download failed: {exc}") from exc


def delete_object(object_key: str, *, bucket: str | None = None) -> None:
    client = _s3_client()
    resolved_bucket = _resolve_bucket(bucket)
    try:
        client.delete_object(Bucket=resolved_bucket, Key=object_key)
    except (ClientError, BotoCoreError) as exc:
        raise StorageOperationError(f"S3 delete failed: {exc}") from exc
