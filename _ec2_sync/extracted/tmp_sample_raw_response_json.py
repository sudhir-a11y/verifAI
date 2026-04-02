from pathlib import Path
import subprocess, os, json
ENV_PATH = Path('/home/ec2-user/qc-python/.env')
env=os.environ.copy()
for raw in ENV_PATH.read_text(encoding='utf-8', errors='ignore').splitlines():
    line=raw.strip().replace('\r','')
    if not line or line.startswith('#') or '=' not in line: continue
    k,v=line.split('=',1)
    env[k.strip()] = v.strip().strip('"').strip("'")
env['PGHOST']=env.get('PG_HOST',''); env['PGPORT']=env.get('PG_PORT',''); env['PGUSER']=env.get('PG_USER',''); env['PGPASSWORD']=env.get('PG_PASSWORD',''); env['PGDATABASE']=env.get('PG_DATABASE','')

sql="""
SELECT decision_payload->>'raw_response_json' AS raw_json
FROM decision_results
WHERE NULLIF(TRIM(COALESCE(decision_payload->>'raw_response_json','')), '') IS NOT NULL
LIMIT 3;
"""
p=subprocess.run(['psql','-X','-A','-t','-F','|','-c',sql],env=env,capture_output=True,text=True)
out=(p.stdout or '').splitlines()
for i,ln in enumerate(out,1):
    t=ln.strip()
    print('SAMPLE',i,'len',len(t))
    print(t[:400])
