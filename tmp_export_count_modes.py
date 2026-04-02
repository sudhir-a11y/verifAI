from app.db.session import SessionLocal
from sqlalchemy import text

d='2026-03-24'
db=SessionLocal()
try:
    q1=text("""
    SELECT COUNT(DISTINCT claim_id)
    FROM workflow_events
    WHERE event_type='claim_assigned' AND DATE(occurred_at)=:d
    """)
    q2=text("""
    SELECT COUNT(*)
    FROM claim_legacy_data l
    WHERE COALESCE(
      CASE
        WHEN NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date','')), '') ~ '^\\d{4}-\\d{2}-\\d{2}$'
          THEN TO_DATE(NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date','')), ''), 'YYYY-MM-DD')
        WHEN NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date','')), '') ~ '^\\d{2}-\\d{2}-\\d{4}$'
          THEN TO_DATE(NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date','')), ''), 'DD-MM-YYYY')
        WHEN NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date','')), '') ~ '^\\d{2}/\\d{2}/\\d{4}$'
          THEN TO_DATE(NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date','')), ''), 'DD/MM/YYYY')
        ELSE NULL
      END,
      NULL
    )=:d
    """)
    q3=text("""
    WITH event_claims AS (
      SELECT DISTINCT claim_id FROM workflow_events WHERE event_type='claim_assigned' AND DATE(occurred_at)=:d
    ),
    legacy_claims AS (
      SELECT claim_id FROM claim_legacy_data l
      WHERE CASE
        WHEN NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date','')), '') ~ '^\\d{4}-\\d{2}-\\d{2}$'
          THEN TO_DATE(NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date','')), ''), 'YYYY-MM-DD')
        WHEN NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date','')), '') ~ '^\\d{2}-\\d{2}-\\d{4}$'
          THEN TO_DATE(NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date','')), ''), 'DD-MM-YYYY')
        WHEN NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date','')), '') ~ '^\\d{2}/\\d{2}/\\d{4}$'
          THEN TO_DATE(NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date','')), ''), 'DD/MM/YYYY')
        ELSE NULL
      END=:d
    )
    SELECT COUNT(DISTINCT claim_id) FROM (
      SELECT claim_id FROM event_claims
      UNION ALL
      SELECT claim_id FROM legacy_claims
    )x
    """)
    print('event_any', int(db.execute(q1,{"d":d}).scalar() or 0))
    print('legacy_alloc', int(db.execute(q2,{"d":d}).scalar() or 0))
    print('union_any', int(db.execute(q3,{"d":d}).scalar() or 0))
finally:
    db.close()
