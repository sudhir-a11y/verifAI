from pathlib import Path
import subprocess
import os

ENV_PATH = Path('/home/ec2-user/qc-python/.env')
if not ENV_PATH.exists():
    raise SystemExit('env file not found')

env = os.environ.copy()
for raw in ENV_PATH.read_text(encoding='utf-8', errors='ignore').splitlines():
    line = raw.strip().replace('\r', '')
    if not line or line.startswith('#') or '=' not in line:
        continue
    k, v = line.split('=', 1)
    env[k.strip()] = v.strip().strip('"').strip("'")

required = ['PG_HOST', 'PG_PORT', 'PG_USER', 'PG_PASSWORD', 'PG_DATABASE']
missing = [k for k in required if not env.get(k)]
if missing:
    raise SystemExit('missing PG vars: ' + ','.join(missing))

env['PGHOST'] = env['PG_HOST']
env['PGPORT'] = env['PG_PORT']
env['PGUSER'] = env['PG_USER']
env['PGPASSWORD'] = env['PG_PASSWORD']
env['PGDATABASE'] = env['PG_DATABASE']

def run_sql(sql: str) -> str:
    proc = subprocess.run(
        ['psql', '-X', '-A', '-t', '-F', '|', '-c', sql],
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or 'psql failed')
    return (proc.stdout or '').strip()

base_cte = """
WITH latest_assignment AS (
    SELECT DISTINCT ON (claim_id)
        claim_id,
        DATE(occurred_at) AS allotment_date
    FROM workflow_events
    WHERE event_type = 'claim_assigned'
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
        COALESCE(
            la.allotment_date,
            CASE
                WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{4}-\\d{2}-\\d{2}$'
                    THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD')
                WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}-\\d{2}-\\d{4}$'
                    THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD-MM-YYYY')
                WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}/\\d{2}/\\d{4}$'
                    THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD/MM/YYYY')
                ELSE NULL
            END,
            DATE(c.updated_at)
        ) AS allotment_date
    FROM claims c
    LEFT JOIN latest_assignment la ON la.claim_id = c.id
    LEFT JOIN legacy_data ldata ON ldata.claim_id = c.id
)
"""

summary_sql = base_cte + """
SELECT
  COUNT(*)::bigint,
  COALESCE(MIN(allotment_date)::text, ''),
  COALESCE(MAX(allotment_date)::text, ''),
  COUNT(*) FILTER (WHERE allotment_date BETWEEN (CURRENT_DATE - INTERVAL '9 day')::date AND CURRENT_DATE)::bigint
FROM base;
"""

top_sql = base_cte + """
SELECT allotment_date::text, COUNT(*)::bigint
FROM base
GROUP BY allotment_date
ORDER BY allotment_date DESC
LIMIT 20;
"""

print('SUMMARY_RAW')
print(run_sql(summary_sql))
print('TOP_RAW')
out = run_sql(top_sql)
print(out if out else '(none)')
