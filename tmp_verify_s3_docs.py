import json
from app.db.session import SessionLocal
from sqlalchemy import text
from app.core.config import settings
import boto3


def parse_metadata(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def resolve_bucket_key(row):
    metadata = parse_metadata(row.get("metadata"))
    bucket = str(metadata.get("bucket") or settings.s3_bucket or "").strip()
    key = str(metadata.get("key") or metadata.get("s3_key") or "").strip()
    storage_uri = str(row.get("storage_uri") or "").strip()

    if (not key) and storage_uri.startswith("s3://"):
        raw = storage_uri[5:]
        first_sep = raw.find("/")
        if first_sep > 0:
            uri_bucket = raw[:first_sep]
            uri_key = raw[first_sep + 1 :]
            if not bucket:
                bucket = uri_bucket
            key = uri_key

    return bucket, key, storage_uri


def safe(value):
    s = str(value or "")
    if len(s) <= 8:
        return s
    return s[:4] + "..." + s[-4:]


def main():
    print("S3 verify start")
    print(f"Configured bucket: {settings.s3_bucket}")
    print(f"Configured region: {settings.s3_region}")

    session = SessionLocal()
    try:
        rows = session.execute(
            text(
                """
                SELECT
                    c.external_claim_id,
                    cd.id,
                    cd.file_name,
                    cd.uploaded_at,
                    cd.storage_uri,
                    cd.metadata
                FROM claim_documents cd
                JOIN claims c ON c.id = cd.claim_id
                ORDER BY cd.uploaded_at DESC NULLS LAST
                LIMIT 20
                """
            )
        ).mappings().all()
    finally:
        session.close()

    if not rows:
        print("No claim_documents rows found.")
        return

    s3 = boto3.client(
        "s3",
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        endpoint_url=(settings.s3_endpoint_url or None),
    )

    ok = 0
    missing = 0
    unresolved = 0

    for idx, row in enumerate(rows, start=1):
        bucket, key, storage_uri = resolve_bucket_key(row)
        label = f"[{idx}] claim={row.get('external_claim_id')} doc={safe(row.get('id'))} file={row.get('file_name')}"

        if not bucket or not key:
            unresolved += 1
            print(f"{label} -> UNRESOLVED bucket/key (storage_uri={storage_uri})")
            continue

        try:
            resp = s3.head_object(Bucket=bucket, Key=key)
            size = int(resp.get("ContentLength") or 0)
            ok += 1
            print(f"{label} -> OK bucket={bucket} key={safe(key)} size={size}")
        except Exception as exc:
            missing += 1
            print(f"{label} -> MISSING/ERROR bucket={bucket} key={safe(key)} err={exc}")

    total = len(rows)
    print("---")
    print(f"Checked rows: {total}")
    print(f"S3 OK: {ok}")
    print(f"S3 Missing/Error: {missing}")
    print(f"Unresolved keys: {unresolved}")


if __name__ == "__main__":
    main()
