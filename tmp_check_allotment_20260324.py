from pathlib import Path
import psycopg

env = {}
for line in Path('/home/ec2-user/qc-python/.env').read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    k, v = line.split('=', 1)
    env[k.strip()] = v.strip()

conn = psycopg.connect(
    host=env.get('PG_HOST', '127.0.0.1'),
    port=int(env.get('PG_PORT', '5432')),
    user=env.get('PG_USER', 'postgres'),
    password=env.get('PG_PASSWORD', ''),
    dbname=env.get('PG_DATABASE', 'postgres'),
)

q1 = '''
WITH event_assignments AS (
    SELECT DISTINCT we.claim_id, DATE(we.occurred_at) AS allotment_date
    FROM workflow_events we
    WHERE we.event_type = 'claim_assigned'
),
legacy_data AS (
    SELECT claim_id, legacy_payload
    FROM claim_legacy_data
),
legacy_assignments AS (
    SELECT
        c.id AS claim_id,
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
    LEFT JOIN legacy_data ldata ON ldata.claim_id = c.id
    WHERE NOT EXISTS (
        SELECT 1
        FROM workflow_events we
        WHERE we.claim_id = c.id
          AND we.event_type = 'claim_assigned'
    )
),
assignment_base AS (
    SELECT claim_id, allotment_date FROM event_assignments
    UNION
    SELECT claim_id, allotment_date FROM legacy_assignments
),
base AS (
    SELECT ab.claim_id, c.status, ab.allotment_date
    FROM assignment_base ab
    JOIN claims c ON c.id = ab.claim_id
    WHERE ab.allotment_date IS NOT NULL
)
SELECT
    COUNT(*) FILTER (WHERE b.status <> 'withdrawn') AS assigned_count,
    COUNT(*) FILTER (WHERE b.status NOT IN ('completed', 'withdrawn')) AS pending_count,
    COUNT(*) FILTER (WHERE b.status = 'completed') AS completed_count
FROM base b
WHERE b.allotment_date = DATE '2026-03-24';
'''

q2 = '''
SELECT COUNT(DISTINCT claim_id)
FROM workflow_events
WHERE event_type = 'claim_assigned'
  AND DATE(occurred_at) = DATE '2026-03-24';
'''

with conn.cursor() as cur:
    cur.execute(q1)
    print('allotment_date_wise_logic:', cur.fetchone())
    cur.execute(q2)
    print('event_distinct_claims:', cur.fetchone())

conn.close()
