from app.db.session import SessionLocal
from sqlalchemy import text


db = SessionLocal()
try:
    q1 = db.execute(text("""
    SELECT status::text AS status, COUNT(*) AS cnt
    FROM claims
    GROUP BY status
    ORDER BY status
    """)).mappings().all()
    print('claim_status_counts')
    for r in q1:
      print(dict(r))

    q2 = db.execute(text("""
    SELECT
      COUNT(*) AS total_completed,
      COUNT(*) FILTER (WHERE cru.claim_id IS NOT NULL) AS has_upload_row,
      COUNT(*) FILTER (WHERE COALESCE(cru.report_export_status,'')='uploaded') AS uploaded_status,
      COUNT(*) FILTER (WHERE NULLIF(TRIM(COALESCE(cru.tagging,'')), '') IS NOT NULL) AS has_tagging,
      COUNT(*) FILTER (WHERE NULLIF(TRIM(COALESCE(cru.subtagging,'')), '') IS NOT NULL) AS has_subtagging,
      COUNT(*) FILTER (WHERE NULLIF(TRIM(COALESCE(cru.opinion,'')), '') IS NOT NULL) AS has_opinion,
      COUNT(*) FILTER (WHERE COALESCE(cru.qc_status,'no')='yes') AS qc_yes,
      COUNT(*) FILTER (WHERE COALESCE(cru.qc_status,'no')='no') AS qc_no
    FROM claims c
    LEFT JOIN claim_report_uploads cru ON cru.claim_id = c.id
    WHERE c.status='completed'
    """)).mappings().first()
    print('completed_upload_meta', dict(q2 or {}))

    q3 = db.execute(text("""
    SELECT
      COUNT(*) FILTER (WHERE NULLIF(TRIM(COALESCE(l.legacy_payload->>'tagging','')), '') IS NOT NULL) AS l_tagging,
      COUNT(*) FILTER (WHERE NULLIF(TRIM(COALESCE(l.legacy_payload->>'subtagging','')), '') IS NOT NULL) AS l_subtagging,
      COUNT(*) FILTER (WHERE NULLIF(TRIM(COALESCE(l.legacy_payload->>'opinion','')), '') IS NOT NULL) AS l_opinion,
      COUNT(*) FILTER (WHERE LOWER(COALESCE(l.legacy_payload->>'report_export_status',''))='uploaded') AS l_uploaded,
      COUNT(*) FILTER (WHERE LOWER(COALESCE(l.legacy_payload->>'qc_status',''))='yes') AS l_qc_yes
    FROM claims c
    LEFT JOIN claim_legacy_data l ON l.claim_id = c.id
    WHERE c.status='completed'
    """)).mappings().first()
    print('completed_legacy_payload_meta', dict(q3 or {}))

    s = db.execute(text("""
    SELECT c.external_claim_id, COALESCE(cru.report_export_status,'') AS report_export_status,
           COALESCE(cru.tagging,'') AS tagging,
           COALESCE(cru.subtagging,'') AS subtagging,
           LEFT(COALESCE(cru.opinion,''),120) AS opinion,
           COALESCE(l.legacy_payload->>'tagging','') AS l_tagging,
           COALESCE(l.legacy_payload->>'subtagging','') AS l_subtagging,
           LEFT(COALESCE(l.legacy_payload->>'opinion',''),120) AS l_opinion,
           LEFT(COALESCE(l.legacy_payload->>'trigger_remarks',''),120) AS l_trigger
    FROM claims c
    LEFT JOIN claim_report_uploads cru ON cru.claim_id=c.id
    LEFT JOIN claim_legacy_data l ON l.claim_id=c.id
    WHERE c.status='completed'
      AND (
        NULLIF(TRIM(COALESCE(l.legacy_payload->>'tagging','')), '') IS NOT NULL
        OR NULLIF(TRIM(COALESCE(l.legacy_payload->>'subtagging','')), '') IS NOT NULL
        OR NULLIF(TRIM(COALESCE(l.legacy_payload->>'opinion','')), '') IS NOT NULL
      )
    ORDER BY c.updated_at DESC
    LIMIT 12
    """)).mappings().all()
    print('sample_rows')
    for r in s:
      print(dict(r))
finally:
    db.close()
