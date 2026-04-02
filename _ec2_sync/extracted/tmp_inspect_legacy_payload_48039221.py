import os
import json
import psycopg

CLAIM_EXTERNAL_ID = '48039221'
ENV_PATH = '/home/ec2-user/qc-python/.env'


def load_env(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for raw in f:
                line = raw.strip().strip('\ufeff')
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass


load_env(ENV_PATH)
conn = psycopg.connect(
    host=os.getenv('PG_HOST', '127.0.0.1'),
    port=int(os.getenv('PG_PORT', '5432')),
    user=os.getenv('PG_USER', 'postgres'),
    password=os.getenv('PG_PASSWORD', ''),
    dbname=os.getenv('PG_DATABASE', 'qc_bkp_modern'),
)

with conn, conn.cursor() as cur:
    cur.execute("SELECT id FROM claims WHERE external_claim_id=%s ORDER BY created_at DESC LIMIT 1", (CLAIM_EXTERNAL_ID,))
    row = cur.fetchone()
    if not row:
        print('claim_not_found')
        raise SystemExit(0)
    cid = row[0]

    cur.execute("SELECT legacy_payload FROM claim_legacy_data WHERE claim_id=%s", (cid,))
    lrow = cur.fetchone()
    if not lrow:
        print('legacy_payload_missing')
        raise SystemExit(0)

    payload = lrow[0] if isinstance(lrow[0], dict) else {}
    print('legacy_payload_keys_count=', len(payload.keys()))
    med_keys = [k for k in payload.keys() if 'med' in str(k).lower() or 'drug' in str(k).lower() or 'rx' in str(k).lower()]
    print('legacy_med_keys=', med_keys)
    for k in med_keys[:20]:
        val = str(payload.get(k, '') or '').strip()
        if len(val) > 220:
            val = val[:220] + '...'
        print(f'{k}={val}')

    cur.execute("SELECT COUNT(*) FROM document_extractions WHERE claim_id=%s", (cid,))
    print('document_extractions_after_reset=', cur.fetchone()[0])

    cur.execute("SELECT COUNT(*) FROM report_versions WHERE claim_id=%s", (cid,))
    print('report_versions_after_sync=', cur.fetchone()[0])
