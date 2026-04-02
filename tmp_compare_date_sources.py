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

queries = {
"events_by_day": '''
SELECT DATE(occurred_at) d, COUNT(DISTINCT claim_id) c
FROM workflow_events
WHERE event_type='claim_assigned' AND DATE(occurred_at) BETWEEN DATE '2026-03-17' AND DATE '2026-03-26'
GROUP BY 1 ORDER BY 1 DESC;
''',
"latest_assignment_by_day": '''
WITH la AS (
  SELECT DISTINCT ON (claim_id) claim_id, DATE(occurred_at) d
  FROM workflow_events
  WHERE event_type='claim_assigned'
  ORDER BY claim_id, occurred_at DESC
)
SELECT d, COUNT(*) c FROM la
WHERE d BETWEEN DATE '2026-03-17' AND DATE '2026-03-26'
GROUP BY 1 ORDER BY 1 DESC;
''',
"legacy_allocation_by_day": '''
WITH l AS (
 SELECT c.id claim_id,
 CASE
  WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), '') ~ '^\\d{4}-\\d{2}-\\d{2}$'
   THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), ''), 'YYYY-MM-DD')
  WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), '') ~ '^\\d{2}-\\d{2}-\\d{4}$'
   THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), ''), 'DD-MM-YYYY')
  WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), '') ~ '^\\d{2}/\\d{2}/\\d{4}$'
   THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), ''), 'DD/MM/YYYY')
  ELSE NULL
 END AS d
 FROM claims c
 LEFT JOIN claim_legacy_data ldata ON ldata.claim_id = c.id
)
SELECT d, COUNT(*) c FROM l
WHERE d BETWEEN DATE '2026-03-17' AND DATE '2026-03-26'
GROUP BY 1 ORDER BY 1 DESC;
''',
"completed_with_opinion_by_legacy_date": '''
WITH l AS (
 SELECT c.id claim_id,
        c.status,
        NULLIF(TRIM(COALESCE(um.opinion,'')), '') AS opinion,
        CASE
          WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), '') ~ '^\\d{4}-\\d{2}-\\d{2}$'
            THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), ''), 'YYYY-MM-DD')
          WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), '') ~ '^\\d{2}-\\d{2}-\\d{4}$'
            THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), ''), 'DD-MM-YYYY')
          WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), '') ~ '^\\d{2}/\\d{2}/\\d{4}$'
            THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), ''), 'DD/MM/YYYY')
          ELSE NULL
        END AS d
 FROM claims c
 LEFT JOIN claim_legacy_data ldata ON ldata.claim_id = c.id
 LEFT JOIN claim_report_uploads um ON um.claim_id = c.id
)
SELECT d, COUNT(*) c FROM l
WHERE d BETWEEN DATE '2026-03-17' AND DATE '2026-03-26'
  AND status='completed' AND opinion IS NOT NULL
GROUP BY 1 ORDER BY 1 DESC;
''',
}

with conn.cursor() as cur:
    for name,q in queries.items():
        print(f'--- {name} ---')
        cur.execute(q)
        for row in cur.fetchall():
            print(row)

conn.close()
