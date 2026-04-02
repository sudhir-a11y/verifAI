from pathlib import Path
import subprocess, os

ENV_PATH = Path('/home/ec2-user/qc-python/.env')
env=os.environ.copy()
for raw in ENV_PATH.read_text(encoding='utf-8', errors='ignore').splitlines():
    line=raw.strip().replace('\r','')
    if not line or line.startswith('#') or '=' not in line or line.startswith('Modern'): continue
    k,v=line.split('=',1)
    env[k.strip()] = v.strip().strip('"').strip("'")
env['PGHOST']=env.get('PG_HOST',''); env['PGPORT']=env.get('PG_PORT',''); env['PGUSER']=env.get('PG_USER',''); env['PGPASSWORD']=env.get('PG_PASSWORD',''); env['PGDATABASE']=env.get('PG_DATABASE','')

sql = '''
WITH latest_extraction AS (
    SELECT DISTINCT ON (claim_id)
        claim_id,
        extracted_entities,
        created_at
    FROM document_extractions
    ORDER BY claim_id, created_at DESC
),
latest_report_version AS (
    SELECT DISTINCT ON (claim_id)
        claim_id,
        report_markdown AS report_html,
        created_at
    FROM report_versions
    WHERE NULLIF(TRIM(COALESCE(report_markdown, '')), '') IS NOT NULL
    ORDER BY claim_id, version_no DESC, created_at DESC
),
latest_decision_report AS (
    SELECT DISTINCT ON (claim_id)
        claim_id,
        NULLIF(TRIM(COALESCE(decision_payload ->> 'report_html', '')), '') AS report_html,
        NULLIF(TRIM(COALESCE(decision_payload ->> 'raw_response_json', '')), '') AS raw_response_json,
        generated_at
    FROM decision_results
    WHERE NULLIF(TRIM(COALESCE(decision_payload ->> 'report_html', '')), '') IS NOT NULL
    ORDER BY claim_id, generated_at DESC
),
final_rows AS (
    SELECT
        c.id,
        c.external_claim_id,
        le.extracted_entities,
        COALESCE(lrv.report_html, ldr.report_html) AS report_html,
        ldr.raw_response_json
    FROM claims c
    LEFT JOIN latest_extraction le ON le.claim_id = c.id
    LEFT JOIN latest_report_version lrv ON lrv.claim_id = c.id
    LEFT JOIN latest_decision_report ldr ON ldr.claim_id = c.id
    WHERE NULLIF(TRIM(COALESCE(lrv.report_html, ldr.report_html, '')), '') IS NOT NULL
)
SELECT
  (SELECT COUNT(*) FROM claims) AS claims_cnt,
  (SELECT COUNT(*) FROM latest_extraction) AS le_cnt,
  (SELECT COUNT(*) FROM latest_report_version) AS lrv_cnt,
  (SELECT COUNT(*) FROM latest_decision_report) AS ldr_cnt,
  (SELECT COUNT(*) FROM final_rows) AS final_cnt,
  (SELECT COUNT(*) FROM final_rows WHERE raw_response_json IS NOT NULL) AS final_with_raw_json;
'''

proc=subprocess.run(['psql','-X','-A','-t','-F','|','-c',sql],env=env,capture_output=True,text=True)
print((proc.stdout or '').strip())
if proc.returncode!=0:
    print('ERR',proc.stderr)
