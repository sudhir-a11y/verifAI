from sqlalchemy import text
from app.db.session import SessionLocal

db=SessionLocal()
try:
    rows = db.execute(text("""
        SELECT claim_id, actor_id, occurred_at, event_payload
        FROM workflow_events
        WHERE event_type='claim_status_updated'
        ORDER BY occurred_at DESC
        LIMIT 20
    """)).mappings().all()
    for r in rows:
        print('---')
        print('claim_id', r['claim_id'])
        print('actor_id', r['actor_id'])
        print('occurred_at', r['occurred_at'])
        print('payload', r['event_payload'])
finally:
    db.close()
