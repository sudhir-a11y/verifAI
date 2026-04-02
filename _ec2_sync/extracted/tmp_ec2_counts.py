from pathlib import Path
import psycopg

env={}
for line in Path('/home/ec2-user/qc-python/.env').read_text().splitlines():
    line=line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    k,v=line.split('=',1)
    env[k.strip()]=v.strip()

conn=psycopg.connect(host=env.get('PG_HOST','127.0.0.1'),port=int(env.get('PG_PORT','5432')),user=env.get('PG_USER','postgres'),password=env.get('PG_PASSWORD',''),dbname=env.get('PG_DATABASE','postgres'))
with conn.cursor() as cur:
    cur.execute('SELECT COUNT(*) FROM claims')
    claims=cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM claim_documents')
    docs=cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM claim_legacy_data')
    legacy=cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM workflow_events')
    we=cur.fetchone()[0]
    cur.execute("SELECT MAX(DATE(occurred_at)) FROM workflow_events WHERE event_type='claim_assigned'")
    latest=cur.fetchone()[0]
    cur.execute("""
        WITH la AS (
          SELECT DISTINCT claim_id
          FROM workflow_events
          WHERE event_type='claim_assigned' AND DATE(occurred_at)=%s
        )
        SELECT COUNT(*), STRING_AGG(c.external_claim_id::text, ',' ORDER BY c.external_claim_id::text)
        FROM claims c JOIN la ON la.claim_id=c.id
    """, (latest,))
    ccount, ids = cur.fetchone()
print(f"EC2_COUNTS claims={claims} docs={docs} legacy={legacy} workflow={we} latest_allotment={latest} latest_claims={ccount}")
print(f"EC2_LATEST_IDS={ids}")
conn.close()
