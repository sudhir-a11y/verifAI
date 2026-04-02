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
WITH event_assignments AS (
    SELECT DISTINCT we.claim_id, DATE(we.occurred_at) AS allotment_date
    FROM workflow_events we
    WHERE we.event_type='claim_assigned'
),
legacy_data AS (
    SELECT claim_id, legacy_payload
    FROM claim_legacy_data
),
legacy_assignments AS (
    SELECT c.id AS claim_id,
        CASE
            WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{4}-\\d{2}-\\d{2}$'
                THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD')
            WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}-\\d{2}-\\d{4}$'
                THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD-MM-YYYY')
            WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}/\\d{2}/\\d{4}$'
                THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD/MM/YYYY')
            ELSE DATE(c.updated_at)
        END AS allotment_date
    FROM claims c
    LEFT JOIN legacy_data ldata ON ldata.claim_id=c.id
    WHERE NOT EXISTS (SELECT 1 FROM workflow_events we WHERE we.claim_id=c.id AND we.event_type='claim_assigned')
),
assignment_base AS (
    SELECT claim_id, allotment_date FROM event_assignments
    UNION
    SELECT claim_id, allotment_date FROM legacy_assignments
),
base AS (
    SELECT ab.claim_id, c.status, ab.allotment_date, NULLIF(TRIM(COALESCE(um.opinion,'')), '') AS opinion
    FROM assignment_base ab
    JOIN claims c ON c.id=ab.claim_id
    LEFT JOIN claim_report_uploads um ON um.claim_id = ab.claim_id
    WHERE ab.allotment_date IS NOT NULL
)
SELECT allotment_date,
       COUNT(*) FILTER (WHERE status <> 'withdrawn') assigned_count,
       COUNT(*) FILTER (WHERE status NOT IN ('completed','withdrawn')) pending_count,
       COUNT(*) FILTER (WHERE status='completed' AND opinion IS NOT NULL) completed_count_nonnull_opinion,
       COUNT(*) FILTER (WHERE status='completed') completed_count_all
FROM base
WHERE allotment_date BETWEEN DATE '2026-03-24' AND DATE '2026-03-26'
GROUP BY allotment_date
ORDER BY allotment_date DESC;
'''

with conn.cursor() as cur:
    cur.execute(q)
    for r in cur.fetchall():
        print(r)

conn.close()
