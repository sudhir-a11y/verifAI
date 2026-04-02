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

q = '''
WITH latest_assignment AS (
  SELECT DATE(occurred_at) AS allotment_date, claim_id
  FROM workflow_events
  WHERE event_type='claim_assigned'
), mx AS (
  SELECT MAX(allotment_date) AS max_date FROM latest_assignment
)
SELECT mx.max_date::text AS max_date, COUNT(*)::int AS claim_count
FROM latest_assignment la
JOIN mx ON la.allotment_date=mx.max_date
GROUP BY mx.max_date
'''
with conn.cursor() as cur:
    cur.execute(q)
    row = cur.fetchone()
    if row:
        print(f"LATEST_ALLOTMENT_DATE={row[0]} CLAIMS={row[1]}")
    else:
        print('LATEST_ALLOTMENT_DATE=<none> CLAIMS=0')

q2 = '''
WITH latest_assignment AS (
  SELECT DATE(occurred_at) AS allotment_date, claim_id
  FROM workflow_events
  WHERE event_type='claim_assigned'
), mx AS (
  SELECT MAX(allotment_date) AS max_date FROM latest_assignment
)
SELECT c.external_claim_id
FROM latest_assignment la
JOIN mx ON la.allotment_date=mx.max_date
JOIN claims c ON c.id=la.claim_id
ORDER BY c.external_claim_id::text
'''
with conn.cursor() as cur:
    cur.execute(q2)
    rows = [str(r[0]) for r in cur.fetchall()]
    print('ALL_CLAIMS=' + ','.join(rows))

conn.close()
