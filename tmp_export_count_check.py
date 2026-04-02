from app.db.session import SessionLocal
from sqlalchemy import text

target='2026-03-24'
db=SessionLocal()
try:
    q_old=text("""
    WITH latest_assignment AS (
      SELECT DISTINCT ON (claim_id) claim_id, DATE(occurred_at) AS allotment_date
      FROM workflow_events
      WHERE event_type='claim_assigned'
      ORDER BY claim_id, occurred_at DESC
    )
    SELECT COUNT(*) AS c
    FROM claims c
    LEFT JOIN latest_assignment la ON la.claim_id=c.id
    WHERE la.allotment_date = :d
    """)
    oldc=int(db.execute(q_old,{"d":target}).scalar() or 0)

    q_new=text("""
    WITH latest_assignment AS (
      SELECT DISTINCT ON (claim_id) claim_id, DATE(occurred_at) AS allotment_date
      FROM workflow_events
      WHERE event_type='claim_assigned'
      ORDER BY claim_id, occurred_at DESC
    ),
    legacy_data AS (
      SELECT claim_id, legacy_payload FROM claim_legacy_data
    )
    SELECT COUNT(*) AS c
    FROM claims c
    LEFT JOIN latest_assignment la ON la.claim_id=c.id
    LEFT JOIN legacy_data ldata ON ldata.claim_id=c.id
    WHERE COALESCE(
      la.allotment_date,
      CASE
        WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), '') ~ '^\\d{4}-\\d{2}-\\d{2}$'
          THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), ''), 'YYYY-MM-DD')
        WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), '') ~ '^\\d{2}-\\d{2}-\\d{4}$'
          THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), ''), 'DD-MM-YYYY')
        WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), '') ~ '^\\d{2}/\\d{2}/\\d{4}$'
          THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date','')), ''), 'DD/MM/YYYY')
        ELSE NULL
      END
    ) = :d
    """)
    newc=int(db.execute(q_new,{"d":target}).scalar() or 0)
    print('old_count', oldc)
    print('new_count', newc)
finally:
    db.close()
