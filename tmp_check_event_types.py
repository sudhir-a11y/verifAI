from pathlib import Path
import subprocess
import os

ENV_PATH = Path('/home/ec2-user/qc-python/.env')
env = os.environ.copy()
for raw in ENV_PATH.read_text(encoding='utf-8', errors='ignore').splitlines():
    line = raw.strip().replace('\r', '')
    if not line or line.startswith('#') or '=' not in line:
        continue
    k, v = line.split('=', 1)
    env[k.strip()] = v.strip().strip('"').strip("'")

env['PGHOST'] = env.get('PG_HOST', '')
env['PGPORT'] = env.get('PG_PORT', '')
env['PGUSER'] = env.get('PG_USER', '')
env['PGPASSWORD'] = env.get('PG_PASSWORD', '')
env['PGDATABASE'] = env.get('PG_DATABASE', '')

sql = """
SELECT event_type, COUNT(*)::bigint
FROM workflow_events
GROUP BY event_type
ORDER BY COUNT(*) DESC;
"""

proc = subprocess.run(['psql', '-X', '-A', '-t', '-F', '|', '-c', sql], env=env, capture_output=True, text=True)
print(proc.stdout.strip())
if proc.returncode != 0:
    print(proc.stderr.strip())
