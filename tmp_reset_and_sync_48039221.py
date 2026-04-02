import os
import json
import urllib.parse
import urllib.request
import psycopg

CLAIM_EXTERNAL_ID = '48039221'
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


load_env_file(ENV_PATH)

pg_host = os.getenv('PG_HOST', '127.0.0.1')
pg_port = int(os.getenv('PG_PORT', '5432'))
pg_user = os.getenv('PG_USER', 'postgres')
pg_password = os.getenv('PG_PASSWORD', '')
pg_database = os.getenv('PG_DATABASE', 'qc_bkp_modern')

sync_url = str(os.getenv('TEAMRIGHTWORKS_SYNC_TRIGGER_URL', '') or '').strip()
sync_key = str(os.getenv('TEAMRIGHTWORKS_SYNC_TRIGGER_KEY', '') or '').strip()

conn = psycopg.connect(
    host=pg_host,
    port=pg_port,
    user=pg_user,
    password=pg_password,
    dbname=pg_database,
)

with conn, conn.cursor() as cur:
    cur.execute(
        """
        SELECT id, external_claim_id, status
        FROM claims
        WHERE external_claim_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (CLAIM_EXTERNAL_ID,),
    )
    row = cur.fetchone()
    if not row:
        print('claim_not_found')
        raise SystemExit(0)

    claim_id = row[0]
    print('claim_uuid=', claim_id)
    print('claim_status_before=', row[2])

    cleanup_stats = {}

    cur.execute("DELETE FROM report_versions WHERE claim_id=%s", (claim_id,))
    cleanup_stats['report_versions_deleted'] = cur.rowcount or 0

    cur.execute("DELETE FROM claim_report_uploads WHERE claim_id=%s", (claim_id,))
    cleanup_stats['claim_report_uploads_deleted'] = cur.rowcount or 0

    cur.execute("DELETE FROM feedback_labels WHERE claim_id=%s", (claim_id,))
    cleanup_stats['feedback_labels_deleted'] = cur.rowcount or 0

    cur.execute("DELETE FROM decision_results WHERE claim_id=%s", (claim_id,))
    cleanup_stats['decision_results_deleted'] = cur.rowcount or 0

    cur.execute("DELETE FROM document_extractions WHERE claim_id=%s", (claim_id,))
    cleanup_stats['document_extractions_deleted'] = cur.rowcount or 0

    cur.execute(
        """
        UPDATE claim_documents
        SET parse_status='pending', parsed_at=NULL
        WHERE claim_id=%s
        """,
        (claim_id,),
    )
    cleanup_stats['documents_reset'] = cur.rowcount or 0

    cur.execute("SELECT to_regclass('public.claim_structured_data')")
    reg = cur.fetchone()[0]
    if reg:
        cur.execute("DELETE FROM claim_structured_data WHERE claim_id=%s", (claim_id,))
        cleanup_stats['claim_structured_data_deleted'] = cur.rowcount or 0
    else:
        cleanup_stats['claim_structured_data_deleted'] = 0

    print('cleanup_stats=', json.dumps(cleanup_stats, ensure_ascii=False))

if not sync_url or not sync_key:
    print('legacy_sync_skipped=missing_config')
    raise SystemExit(0)

params = {
    'key': sync_key,
    'mode': 'single',
    'claim_id': CLAIM_EXTERNAL_ID,
}
full_url = sync_url + ('&' if '?' in sync_url else '?') + urllib.parse.urlencode(params)
req = urllib.request.Request(full_url, method='GET')

print('legacy_sync_url_host=', urllib.parse.urlparse(sync_url).netloc)
print('legacy_sync_mode=single')
print('legacy_sync_claim_id=', CLAIM_EXTERNAL_ID)

try:
    with urllib.request.urlopen(req, timeout=90) as resp:
        body = resp.read().decode('utf-8', errors='replace')
        status = int(getattr(resp, 'status', 200))
except Exception as exc:
    print('legacy_sync_error=', str(exc))
    raise SystemExit(0)

print('legacy_sync_http_status=', status)
try:
    parsed = json.loads(body)
except Exception:
    parsed = {'raw': body[:2000]}

print('legacy_sync_response=', json.dumps(parsed, ensure_ascii=False)[:3000])
