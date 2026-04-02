from sqlalchemy import text
from app.db.session import SessionLocal

db=SessionLocal()
try:
    rows = db.execute(text("""
        SELECT LOWER(COALESCE(actor_id,'')) AS actor_key,
               TO_CHAR(DATE_TRUNC('month', occurred_at AT TIME ZONE 'Asia/Kolkata'), 'YYYY-MM') AS month_key,
               COUNT(*)::integer AS cnt
        FROM workflow_events
        WHERE event_type='claim_status_updated'
          AND COALESCE(event_payload->>'status','')='completed'
          AND LOWER(COALESCE(actor_id,'')) IN ('sapna','spana','drsapna')
        GROUP BY LOWER(COALESCE(actor_id,'')), DATE_TRUNC('month', occurred_at AT TIME ZONE 'Asia/Kolkata')
        ORDER BY month_key DESC, actor_key ASC
    """)).mappings().all()
    print('ACTOR_COMPLETED_EVENTS')
    for r in rows:
        print(dict(r))
finally:
    db.close()
