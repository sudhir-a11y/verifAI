from pathlib import Path
import psycopg

env = {}
for line in Path('/home/ec2-user/qc-python/.env').read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    k,v = line.split('=',1)
    env[k.strip()] = v.strip()

conn = psycopg.connect(
    host=env.get('PG_HOST','127.0.0.1'),
    port=int(env.get('PG_PORT','5432')),
    user=env.get('PG_USER','postgres'),
    password=env.get('PG_PASSWORD',''),
    dbname=env.get('PG_DATABASE','postgres'),
)

q='''
WITH latest_assignment AS (
    SELECT DISTINCT ON (claim_id)
        claim_id,
        DATE(occurred_at) AS allotment_date
    FROM workflow_events
    WHERE event_type='claim_assigned'
    ORDER BY claim_id, occurred_at DESC
),
legacy_data AS (
    SELECT claim_id, legacy_payload
    FROM claim_legacy_data
),
base AS (
    SELECT
        c.id AS claim_id,
        c.status,
        NULLIF(TRIM(COALESCE(um.opinion, '')), '') AS opinion,
        COALESCE(
            CASE
                WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{4}-\\d{2}-\\d{2}$'
                    THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD')
                WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{4}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}:\\d{2}$'
                    THEN TO_TIMESTAMP(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD HH24:MI:SS')::date
                WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}-\\d{2}-\\d{4}$'
                    THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD-MM-YYYY')
                WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}/\\d{2}/\\d{4}$'
                    THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD/MM/YYYY')
                ELSE NULL
            END,
            la.allotment_date,
            DATE(c.updated_at)
        ) AS allotment_date
    FROM claims c
    LEFT JOIN latest_assignment la ON la.claim_id = c.id
    LEFT JOIN legacy_data ldata ON ldata.claim_id = c.id
    LEFT JOIN claim_report_uploads um ON um.claim_id = c.id
)
SELECT allotment_date,
       COUNT(*) FILTER (WHERE status <> 'withdrawn') AS assigned_count,
       COUNT(*) FILTER (WHERE status NOT IN ('completed', 'withdrawn')) AS pending_count,
       COUNT(*) FILTER (WHERE status='completed' AND opinion IS NOT NULL) AS completed_with_opinion,
       COUNT(*) FILTER (WHERE status='completed') AS completed_all
FROM base
WHERE allotment_date BETWEEN DATE '2026-03-24' AND DATE '2026-03-26'
GROUP BY 1
ORDER BY 1 DESC;
'''

with conn.cursor() as cur:
    cur.execute(q)
    for r in cur.fetchall():
        print(r)

conn.close()
