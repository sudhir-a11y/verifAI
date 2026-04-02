from app.db.session import SessionLocal
from sqlalchemy import text

db=SessionLocal()
try:
    r = db.execute(text("""
    SELECT
      COUNT(*) FILTER (
        WHERE NULLIF(TRIM(COALESCE(cru.tagging,'')), '') IS NOT NULL
          AND NULLIF(TRIM(COALESCE(cru.subtagging,'')), '') IS NOT NULL
          AND NULLIF(TRIM(COALESCE(cru.opinion,'')), '') IS NOT NULL
      ) AS effective_uploaded,
      COUNT(*) FILTER (
        WHERE NOT (
          NULLIF(TRIM(COALESCE(cru.tagging,'')), '') IS NOT NULL
          AND NULLIF(TRIM(COALESCE(cru.subtagging,'')), '') IS NOT NULL
          AND NULLIF(TRIM(COALESCE(cru.opinion,'')), '') IS NOT NULL
        )
      ) AS effective_pending,
      COUNT(*) AS total_completed,
      COUNT(*) FILTER (WHERE LOWER(COALESCE(cru.qc_status,'no'))='no') AS qc_no
    FROM claims c
    LEFT JOIN claim_report_uploads cru ON cru.claim_id=c.id
    WHERE c.status='completed'
    """)).mappings().first()
    print(dict(r or {}))

    r2 = db.execute(text("SELECT status::text AS status, COUNT(*) AS cnt FROM claims GROUP BY status ORDER BY status")).mappings().all()
    print([dict(x) for x in r2])
finally:
    db.close()
