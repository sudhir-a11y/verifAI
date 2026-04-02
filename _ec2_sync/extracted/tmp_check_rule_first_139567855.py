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
    d = out.model_dump()
    print('recommendation', d.get('recommendation'))
    print('route_target', d.get('route_target'))
    payload = (d.get('source_summary') or {})
    print('reporting_rule_locked', ((payload.get('reporting') or {}).get('rule_locked_by_trigger')))
    print('openai_merged_used', ((payload.get('openai_merged_review') or {}).get('used')))

    latest = db.execute(text('''
        SELECT recommendation, explanation_summary, decision_payload
        FROM decision_results
        WHERE claim_id = :claim_id
        ORDER BY generated_at DESC
        LIMIT 1
    '''), {'claim_id': str(claim_uuid)}).mappings().first()
    print('db_recommendation', latest.get('recommendation'))
    summary = str(latest.get('explanation_summary') or '')
    print('summary_has_learning_signal', 'Learning signal:' in summary)
    print('summary_head', summary[:240])
finally:
    db.close()
