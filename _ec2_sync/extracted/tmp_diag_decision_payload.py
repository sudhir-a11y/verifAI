from app.db.session import SessionLocal
from sqlalchemy import text


db=SessionLocal()
try:
    q = db.execute(text("""
    SELECT
      COUNT(*) FILTER (WHERE LOWER(COALESCE(decision_payload->>'tagging','')) <> '') AS dp_tagging,
      COUNT(*) FILTER (WHERE LOWER(COALESCE(decision_payload->>'subtagging','')) <> '') AS dp_subtagging,
      COUNT(*) FILTER (WHERE LOWER(COALESCE(decision_payload->>'opinion','')) <> '') AS dp_opinion,
      COUNT(*) FILTER (WHERE LOWER(COALESCE(decision_payload->>'report_export_status','')) = 'uploaded') AS dp_uploaded,
      COUNT(*) FILTER (WHERE LOWER(COALESCE(decision_payload->>'final_recommendation','')) <> '') AS dp_final_reco,
      COUNT(*) FILTER (WHERE LOWER(COALESCE(decision_payload->>'recommendation','')) <> '') AS dp_recommendation
    FROM decision_results
    WHERE is_active = TRUE
    """)).mappings().first()
    print('decision_payload_counts', dict(q or {}))

    rows = db.execute(text("""
    SELECT c.external_claim_id,
           dr.recommendation::text AS reco,
           LEFT(COALESCE(dr.explanation_summary,''),120) AS expl,
           LEFT(COALESCE(cru.opinion,''),120) AS current_opinion,
           LEFT(COALESCE(dr.decision_payload->>'opinion',''),120) AS dp_opinion,
           COALESCE(dr.decision_payload->>'tagging','') AS dp_tagging,
           COALESCE(dr.decision_payload->>'subtagging','') AS dp_subtagging
    FROM claims c
    JOIN decision_results dr ON dr.claim_id=c.id AND dr.is_active = TRUE
    LEFT JOIN claim_report_uploads cru ON cru.claim_id=c.id
    WHERE c.status='completed'
    ORDER BY c.updated_at DESC
    LIMIT 20
    """)).mappings().all()
    for r in rows:
        print(dict(r))
finally:
    db.close()
