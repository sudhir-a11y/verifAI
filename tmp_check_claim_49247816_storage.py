import os
from pathlib import Path
from urllib.parse import urlparse, unquote
import psycopg
import boto3
from botocore.exceptions import ClientError

CLAIM_EXTERNAL_ID = '49247816'
CLAIM_UUID = '479afafb-7682-4581-a180-b6440e38fae2'
ENV_PATH = '/home/ec2-user/qc-python/.env'


def load_env_file(path: str) -> None:
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for raw in f:
                line = raw.strip().strip('\ufeff')
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except FileNotFoundError:
        pass


def parse_s3_url(url: str):
    u = (url or '').strip()
    if not u:
        return ('', '')
    p = urlparse(u)
    host = (p.netloc or '').lower()
    path = unquote((p.path or '').lstrip('/'))
    if '.s3.' in host and host.endswith('amazonaws.com'):
        bucket = host.split('.s3.', 1)[0]
        return (bucket, path)
    if host.startswith('s3.') and host.endswith('amazonaws.com') and '/' in path:
        bucket, key = path.split('/', 1)
        return (bucket, key)
    return ('', '')


def head_exists(s3_client, bucket: str, key: str):
    if not bucket or not key:
        return 'missing_bucket_or_key'
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return 'exists'
    except ClientError as exc:
        code = str(((exc.response or {}).get('Error') or {}).get('Code') or '')
        return f'error:{code or "unknown"}'


load_env_file(ENV_PATH)

conn = psycopg.connect(
    host=os.getenv('PG_HOST', '127.0.0.1'),
    port=int(os.getenv('PG_PORT', '5432')),
    user=os.getenv('PG_USER', 'postgres'),
    password=os.getenv('PG_PASSWORD', ''),
    dbname=os.getenv('PG_DATABASE', 'qc_bkp_modern'),
)

s3 = boto3.client(
    's3',
    region_name=os.getenv('S3_REGION') or 'ap-south-1',
    endpoint_url=(os.getenv('S3_ENDPOINT_URL') or None),
    aws_access_key_id=(os.getenv('S3_ACCESS_KEY') or None),
    aws_secret_access_key=(os.getenv('S3_SECRET_KEY') or None),
)

default_bucket = (os.getenv('S3_BUCKET') or '').strip()

with conn, conn.cursor() as cur:
    cur.execute(
        """
        SELECT id::text, external_claim_id, status, assigned_doctor_id
        FROM claims
        WHERE external_claim_id = %s OR id::text = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (CLAIM_EXTERNAL_ID, CLAIM_UUID),
    )
    claim = cur.fetchone()
    if not claim:
        print('claim_not_found')
        raise SystemExit(0)

    claim_id = claim[0]
    print('claim_id=', claim_id)
    print('external_claim_id=', claim[1])
    print('status=', claim[2])
    print('assigned_doctor_id=', claim[3])
    print('default_bucket=', default_bucket)

    cur.execute(
        """
        SELECT id::text,
               file_name,
               storage_key,
               uploaded_at,
               COALESCE(metadata->>'storage_provider','') AS storage_provider,
               COALESCE(metadata->>'s3_url','') AS s3_url,
               COALESCE(metadata->>'legacy_s3_url','') AS legacy_s3_url,
               COALESCE(metadata->>'external_url','') AS external_url,
               COALESCE(metadata->>'external_document_url','') AS external_document_url
        FROM claim_documents
        WHERE claim_id = %s
        ORDER BY uploaded_at ASC
        """,
        (claim_id,),
    )
    rows = cur.fetchall()

    print('document_count=', len(rows))
    for r in rows:
        doc_id, file_name, storage_key, uploaded_at, provider, s3_url, legacy_s3_url, external_url, external_document_url = r
        storage_key = storage_key or ''
        exists_main = head_exists(s3, default_bucket, storage_key)

        url_bucket, url_key = parse_s3_url(s3_url or legacy_s3_url or external_url or external_document_url)
        exists_url = head_exists(s3, url_bucket, url_key) if (url_bucket and url_key) else 'n/a'

        print('---')
        print('doc_id=', doc_id)
        print('file_name=', file_name)
        print('uploaded_at=', uploaded_at)
        print('storage_provider=', provider)
        print('storage_key=', storage_key)
        print('exists_default_bucket=', exists_main)
        if s3_url:
            print('s3_url=', s3_url)
        if legacy_s3_url:
            print('legacy_s3_url=', legacy_s3_url)
        if external_url:
            print('external_url=', external_url)
        if external_document_url:
            print('external_document_url=', external_document_url)
        if url_bucket:
            print('url_bucket=', url_bucket)
            print('url_key=', url_key)
            print('exists_url_bucket=', exists_url)
