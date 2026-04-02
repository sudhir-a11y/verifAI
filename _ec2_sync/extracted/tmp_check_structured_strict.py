from uuid import UUID
from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.claim_structuring_service import generate_claim_structured_data

TARGET_CLAIM_ID = '139567855'

db = SessionLocal()
try:
    row = db.execute(text('SELECT id FROM claims WHERE external_claim_id = :cid LIMIT 1'), {'cid': TARGET_CLAIM_ID}).mappings().first()
    if not row:
        print('claim_not_found')
        raise SystemExit(0)
    claim_uuid = UUID(str(row['id']))
    out = generate_claim_structured_data(db=db, claim_id=claim_uuid, actor_id='system-check', use_llm=True, force_refresh=True)
    print('source', out.get('source'))
    raw = out.get('raw_payload') or {}
    ls = raw.get('learning_signals') if isinstance(raw, dict) else {}
    print('learning_signals', ls)
    print('recommendation', out.get('recommendation'))
    print('conclusion_head', str(out.get('conclusion') or '')[:220])
    db.commit()
finally:
    db.close()
