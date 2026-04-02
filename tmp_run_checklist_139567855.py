from uuid import UUID
from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.checklist_pipeline import run_claim_checklist_pipeline

TARGET_CLAIM_ID = '139567855'

db = SessionLocal()
try:
    row = db.execute(text('SELECT id FROM claims WHERE external_claim_id = :cid LIMIT 1'), {'cid': TARGET_CLAIM_ID}).mappings().first()
    if not row:
        print('claim_not_found')
        raise SystemExit(0)
    claim_uuid = UUID(str(row['id']))
    out = run_claim_checklist_pipeline(db=db, claim_id=claim_uuid, actor_id='system-check', force_source_refresh=True)
    data = out.model_dump()
    print('keys', sorted(list(data.keys())))
    print('recommendation', data.get('recommendation'))
    checklist = data.get('checklist') or []
    print('entries_count', len(checklist))
    src = data.get('source_summary') or {}
    report_html = str(src.get('report_html') or '')
    print('report_html_len', len(report_html))
    print('report_html_head', report_html[:220].replace('\n',' '))
finally:
    db.close()
