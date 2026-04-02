from pathlib import Path
import subprocess, os
ENV_PATH = Path('/home/ec2-user/qc-python/.env')
env=os.environ.copy()
for raw in ENV_PATH.read_text(encoding='utf-8', errors='ignore').splitlines():
    line=raw.strip().replace('\r','')
    if not line or line.startswith('#') or '=' not in line:
        continue
    k,v=line.split('=',1)
    env[k.strip()] = v.strip().strip('"').strip("'")
env['PGHOST']=env.get('PG_HOST',''); env['PGPORT']=env.get('PG_PORT',''); env['PGUSER']=env.get('PG_USER',''); env['PGPASSWORD']=env.get('PG_PASSWORD',''); env['PGDATABASE']=env.get('PG_DATABASE','')

def run(sql):
    p=subprocess.run(['psql','-X','-A','-t','-F','|','-c',sql],env=env,capture_output=True,text=True)
    if p.returncode!=0:
        print('ERR',p.stderr.strip())
    return (p.stdout or '').strip()

print('MODEL_REGISTRY_COLUMNS')
print(run("""
SELECT column_name FROM information_schema.columns
WHERE table_name='model_registry'
ORDER BY ordinal_position;
"""))

print('MODEL_REGISTRY_ROWS')
print(run("""
SELECT * FROM model_registry ORDER BY created_at DESC LIMIT 3;
"""))

print('RECENT_ML_RETRAIN_LOG_HINT')
print(run("""
SELECT COUNT(*)::bigint FROM workflow_events
WHERE event_type='claim_checklist_evaluated'
  AND occurred_at >= NOW() - INTERVAL '7 days';
"""))
