from sqlalchemy import text
from app.db.session import SessionLocal

db=SessionLocal()
try:
    sql = """
    WITH latest_assignment AS (
        SELECT DISTINCT ON (claim_id)
            claim_id,
            DATE(occurred_at) AS allotment_date
        FROM workflow_events
        WHERE event_type = 'claim_assigned'
        ORDER BY claim_id, occurred_at DESC
    ),
    legacy_data AS (
        SELECT claim_id, legacy_payload
        FROM claim_legacy_data
    ),
    completed_base AS (
        SELECT
            c.id AS claim_id,
            COALESCE(c.assigned_doctor_id, '') AS assigned_doctor_id,
            COALESCE(
                la.allotment_date,
                CASE
                    WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\d{4}-\d{2}-\d{2}$'
                        THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD')
                    WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\d{2}-\d{2}-\d{4}$'
                        THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD-MM-YYYY')
                    WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\d{2}/\d{2}/\d{4}$'
                        THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD/MM/YYYY')
                    ELSE NULL
                END,
                DATE(c.updated_at)
            ) AS effective_allotment_date
        FROM claims c
        LEFT JOIN latest_assignment la ON la.claim_id = c.id
        LEFT JOIN legacy_data ldata ON ldata.claim_id = c.id
        WHERE c.status='completed'
    ),
    tokens AS (
      SELECT cb.claim_id, cb.effective_allotment_date,
             CASE WHEN token IN ('spana','drsapna') THEN 'sapna' ELSE token END AS doctor_key
      FROM completed_base cb
      CROSS JOIN LATERAL unnest(
         string_to_array(regexp_replace(LOWER(COALESCE(cb.assigned_doctor_id,'')), '[^a-z0-9,]+', '', 'g'), ',')
      ) AS token
      WHERE NULLIF(token,'') IS NOT NULL
    )
    SELECT
      SUM(CASE WHEN effective_allotment_date >= DATE '2026-03-01' AND effective_allotment_date < DATE '2026-04-01' THEN 1 ELSE 0 END)::int AS mar_cnt,
      SUM(CASE WHEN effective_allotment_date >= DATE '2026-04-01' AND effective_allotment_date < DATE '2026-05-01' THEN 1 ELSE 0 END)::int AS apr_cnt,
      COUNT(*)::int AS total_cnt
    FROM tokens
    WHERE doctor_key='sapna'
    """
    r=db.execute(text(sql)).mappings().first()
    print(dict(r))
finally:
    db.close()
