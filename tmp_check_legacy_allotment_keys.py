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

q = '''
SELECT
  COUNT(*) FILTER (WHERE legacy_payload ? 'allocation_date') AS has_allocation_date,
  COUNT(*) FILTER (WHERE legacy_payload ? 'allotment_date') AS has_allotment_date,
  COUNT(*) FILTER (WHERE legacy_payload ? 'allotment date') AS has_allotment_date_space,
  COUNT(*) FILTER (WHERE legacy_payload ? 'alloted_date') AS has_alloted_date,
  COUNT(*) FILTER (WHERE legacy_payload ? 'alloted date') AS has_alloted_date_space
FROM claim_legacy_data;
'''

q2 = '''
SELECT
  COALESCE(legacy_payload->>'allocation_date', legacy_payload->>'allotment_date', legacy_payload->>'allotment date', legacy_payload->>'alloted_date', legacy_payload->>'alloted date') AS raw_date,
  COUNT(*)
FROM claim_legacy_data
GROUP BY 1
ORDER BY COUNT(*) DESC
LIMIT 20;
'''

with conn.cursor() as cur:
    cur.execute(q)
    print('key_presence=', cur.fetchone())
    cur.execute(q2)
    print('top_raw_dates:')
    for r in cur.fetchall():
        print(r)

conn.close()
