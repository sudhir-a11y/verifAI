from app.db.session import SessionLocal
from sqlalchemy import text

d='2026-03-24'
db=SessionLocal()
try:
    q=text("""
    SELECT COUNT(*)
    FROM claims c
    LEFT JOIN claim_legacy_data ldata ON ldata.claim_id = c.id
    WHERE (
      EXISTS (
        SELECT 1 FROM workflow_events we
        WHERE we.claim_id = c.id
          AND we.event_type = 'claim_assigned'
          AND DATE(we.occurred_at) = :d
      )
      OR
      CASE
        WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), '') ~ '^\\d{4}-\\d{2}-\\d{2}$'
          THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), ''), 'YYYY-MM-DD')
        WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), '') ~ '^\\d{2}-\\d{2}-\\d{4}$'
          THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), ''), 'DD-MM-YYYY')
        WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), '') ~ '^\\d{2}/\\d{2}/\\d{4}$'
          THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), ''), 'DD/MM/YYYY')
        ELSE NULL
      END = :d
    )
    """)
    print('filtered_count', int(db.execute(q,{"d":d}).scalar() or 0))
finally:
    db.close()
