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

with conn.cursor() as cur:
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema='public'
          AND (table_name ILIKE '%excel%' OR table_name ILIKE '%upload%' OR table_name ILIKE '%claim%')
        ORDER BY table_name
    """)
    tables = [r[0] for r in cur.fetchall()]
    print('tables=', tables)

    for t in ['excel_upload_data', 'claim_report_uploads', 'claim_legacy_data', 'workflow_events', 'claims']:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name=%s
            )
        """, (t,))
        exists = cur.fetchone()[0]
        print(f'table_exists:{t}={exists}')
        if exists:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=%s
                ORDER BY ordinal_position
            """, (t,))
            cols = [r[0] for r in cur.fetchall()]
            print(f'columns:{t}={cols}')

conn.close()
