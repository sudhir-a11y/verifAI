import os
from pathlib import Path
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text

for line in Path('/home/ec2-user/qc-python/.env').read_text(encoding='utf-8').splitlines():
    line=line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    k,v=line.split('=',1)
    os.environ[k.strip()] = v.strip().strip('"').strip("'")

uri = f"postgresql+psycopg://{quote_plus(os.environ.get('PG_USER','postgres'))}:{quote_plus(os.environ.get('PG_PASSWORD','postgres'))}@{os.environ.get('PG_HOST','127.0.0.1')}:{int(os.environ.get('PG_PORT','5432'))}/{quote_plus(os.environ.get('PG_DATABASE','qc_bkp_modern'))}?connect_timeout=5"
engine = create_engine(uri)

sql = '''
WITH latest_report AS (
    SELECT DISTINCT ON (claim_id)
        claim_id, export_uri
    FROM report_versions
    ORDER BY claim_id, version_no DESC
),
upload_meta AS (
    SELECT
        claim_id,
        report_export_status,
        tagging,
        subtagging,
        opinion,
        qc_status
    FROM claim_report_uploads
),
base AS (
    SELECT
        c.id,
        c.status::text AS claim_status,
        CASE
            WHEN NULLIF(TRIM(COALESCE(um.tagging, '')), '') IS NOT NULL
                 OR NULLIF(TRIM(COALESCE(um.subtagging, '')), '') IS NOT NULL
                 OR NULLIF(TRIM(COALESCE(um.opinion, '')), '') IS NOT NULL
            THEN 'uploaded'
            WHEN COALESCE(um.report_export_status, 'pending') = 'uploaded'
            THEN 'uploaded'
            WHEN COALESCE(rv.export_uri, '') <> ''
            THEN 'uploaded'
            ELSE 'pending'
        END AS effective_report_status,
        CASE
            WHEN LOWER(REPLACE(REPLACE(COALESCE(um.qc_status, 'no'), ' ', '_'), '-', '_')) IN ('yes', 'qc_yes', 'qcyes', 'qc_done', 'done')
            THEN 'yes' ELSE 'no'
        END AS qc_status
    FROM claims c
    LEFT JOIN latest_report rv ON rv.claim_id = c.id
    LEFT JOIN upload_meta um ON um.claim_id = c.id
)
SELECT
    COUNT(*) FILTER (WHERE claim_status = 'completed') AS completed_total,
    COUNT(*) FILTER (WHERE claim_status = 'completed' AND effective_report_status = 'uploaded') AS completed_uploaded_all_qc,
    COUNT(*) FILTER (WHERE claim_status = 'completed' AND effective_report_status = 'uploaded' AND qc_status = 'no') AS completed_uploaded_qc_no,
    COUNT(*) FILTER (WHERE claim_status = 'completed' AND effective_report_status = 'uploaded' AND qc_status = 'yes') AS completed_uploaded_qc_yes
FROM base;
'''

with engine.connect() as conn:
    row = conn.execute(text(sql)).mappings().first()
    print(dict(row or {}))
