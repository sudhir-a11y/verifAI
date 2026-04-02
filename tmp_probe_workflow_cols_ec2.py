from sqlalchemy import text
from app.db.session import SessionLocal

db = SessionLocal()
try:
    cols = db.execute(text("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name='workflow_events'
        ORDER BY ordinal_position
    """)).mappings().all()
    print('WORKFLOW_EVENT_COLUMNS')
    for c in cols:
        print(dict(c))

    sample = db.execute(text("""
        SELECT *
        FROM workflow_events
        ORDER BY occurred_at DESC
        LIMIT 3
    """)).mappings().all()
    print('SAMPLE_ROWS_KEYS')
    if sample:
        print(list(sample[0].keys()))
        for r in sample:
            print({k:r[k] for k in list(r.keys())[:8]})
finally:
    db.close()
