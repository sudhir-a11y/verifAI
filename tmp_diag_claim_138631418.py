import os
from pathlib import Path
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text

ENV_PATH = Path('/home/ec2-user/qc-python/.env')
for line in ENV_PATH.read_text(encoding='utf-8').splitlines():
    line = line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    k, v = line.split('=', 1)
    os.environ[k.strip()] = v.strip().strip('"').strip("'")

uri = f"postgresql+psycopg://{quote_plus(os.environ.get('PG_USER','postgres'))}:{quote_plus(os.environ.get('PG_PASSWORD','postgres'))}@{os.environ.get('PG_HOST','127.0.0.1')}:{int(os.environ.get('PG_PORT','5432'))}/{quote_plus(os.environ.get('PG_DATABASE','qc_bkp_modern'))}?connect_timeout=5"
engine = create_engine(uri)
claim_ext = '138631418'

with engine.connect() as conn:
    claim = conn.execute(text('SELECT id::text AS id FROM claims WHERE external_claim_id=:cid LIMIT 1'), {'cid': claim_ext}).mappings().first()
    print('CLAIM=', dict(claim) if claim else None)
    if not claim:
        raise SystemExit(0)
    cid = claim['id']

    legacy = conn.execute(text('''
      SELECT
        LENGTH(COALESCE(legacy_payload::text,'')) AS payload_len,
        legacy_payload ? 'report_html' AS has_report_html_key,
        legacy_payload ? 'doctor_report_html' AS has_doctor_report_html_key,
        legacy_payload ? 'system_report_html' AS has_system_report_html_key,
        LENGTH(COALESCE(legacy_payload->>'report_html','')) AS report_html_len,
        LENGTH(COALESCE(legacy_payload->>'doctor_report_html','')) AS doctor_report_html_len,
        LENGTH(COALESCE(legacy_payload->>'system_report_html','')) AS system_report_html_len
      FROM claim_legacy_data
      WHERE claim_id=:cid
      LIMIT 1
    '''), {'cid': cid}).mappings().first()
    print('LEGACY=', dict(legacy) if legacy else None)

    up = conn.execute(text('''
      SELECT report_export_status, tagging, subtagging, opinion, qc_status, updated_at
      FROM claim_report_uploads
      WHERE claim_id=:cid
      LIMIT 1
    '''), {'cid': cid}).mappings().first()
    print('UPLOAD_META=', dict(up) if up else None)

    events = conn.execute(text('''
      SELECT event_type, actor_id, occurred_at,
             LENGTH(COALESCE(event_payload::text,'')) AS payload_len,
             LENGTH(COALESCE(event_payload->>'report_html','')) AS report_html_len
      FROM workflow_events
      WHERE claim_id=:cid
      ORDER BY occurred_at DESC
      LIMIT 10
    '''), {'cid': cid}).mappings().all()
    print('WORKFLOW_EVENTS=', len(events))
    for e in events:
      print('EV=', dict(e))
