from pathlib import Path
import subprocess, os
ENV_PATH = Path('/home/ec2-user/qc-python/.env')
env=os.environ.copy()
for raw in ENV_PATH.read_text(encoding='utf-8', errors='ignore').splitlines():
    line=raw.strip().replace('\r','')
    if not line or line.startswith('#') or '=' not in line: continue
    k,v=line.split('=',1)
    env[k.strip()] = v.strip().strip('"').strip("'")
env['PGHOST']=env.get('PG_HOST',''); env['PGPORT']=env.get('PG_PORT',''); env['PGUSER']=env.get('PG_USER',''); env['PGPASSWORD']=env.get('PG_PASSWORD',''); env['PGDATABASE']=env.get('PG_DATABASE','')

def q(sql):
    p=subprocess.run(['psql','-X','-A','-t','-F','|','-c',sql],env=env,capture_output=True,text=True)
    print((p.stdout or '').strip())
    if p.returncode!=0: print('ERR',p.stderr.strip())

print('decision_results_total')
q("SELECT COUNT(*)::bigint FROM decision_results;")
print('decision_payload_has_extracted_entities')
q("SELECT COUNT(*)::bigint FROM decision_results WHERE decision_payload ? 'extracted_entities';")
print('decision_payload_has_report_html')
q("SELECT COUNT(*)::bigint FROM decision_results WHERE NULLIF(TRIM(COALESCE(decision_payload->>'report_html','')), '') IS NOT NULL;")
print('document_extractions_total')
q("SELECT COUNT(*)::bigint FROM document_extractions;")
print('claims_with_latest_extraction')
q("SELECT COUNT(DISTINCT claim_id)::bigint FROM document_extractions;")
print('decision_payload_sample_keys')
q("SELECT jsonb_object_keys(decision_payload) FROM decision_results WHERE decision_payload IS NOT NULL LIMIT 30;")
