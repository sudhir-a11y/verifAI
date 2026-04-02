import os
from pathlib import Path
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text

for line in Path('/home/ec2-user/qc-python/.env').read_text(encoding='utf-8').splitlines():
    line=line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    k,v=line.split('=',1)
    os.environ[k.strip()]=v.strip().strip('"').strip("'")

uri = f"postgresql+psycopg://{quote_plus(os.environ.get('PG_USER','postgres'))}:{quote_plus(os.environ.get('PG_PASSWORD','postgres'))}@{os.environ.get('PG_HOST','127.0.0.1')}:{int(os.environ.get('PG_PORT','5432'))}/{quote_plus(os.environ.get('PG_DATABASE','qc_bkp_modern'))}?connect_timeout=5"
engine=create_engine(uri)
claim='138631418'
with engine.connect() as conn:
    row=conn.execute(text("SELECT id::text FROM claims WHERE external_claim_id=:c LIMIT 1"),{'c':claim}).mappings().first()
    print('claim_uuid=', row['id'] if row else None)
    if row:
        cid=row['id']
        rv=conn.execute(text("SELECT count(*) AS cnt, COALESCE(max(version_no),0) AS max_v FROM report_versions WHERE claim_id=:cid"),{'cid':cid}).mappings().first()
        dr=conn.execute(text("SELECT count(*) AS cnt FROM decision_results WHERE claim_id=:cid"),{'cid':cid}).mappings().first()
        print('report_versions=', dict(rv))
        print('decision_results=', dict(dr))
