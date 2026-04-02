from sqlalchemy import text
from app.db.session import SessionLocal

db = SessionLocal()
try:
    queries = {
        'A_mar': """
            WITH tokens AS (
                SELECT c.id AS claim_id,
                       CASE WHEN token IN ('spana','drsapna') THEN 'sapna' ELSE token END AS doctor_key
                FROM claims c
                CROSS JOIN LATERAL unnest(string_to_array(regexp_replace(LOWER(COALESCE(c.assigned_doctor_id,'')), '[^a-z0-9,]+', '', 'g'), ',')) AS token
                WHERE c.status='completed'
                  AND c.updated_at IS NOT NULL
                  AND DATE(c.updated_at) >= DATE '2026-03-01'
                  AND DATE(c.updated_at) < DATE '2026-04-01'
                  AND NULLIF(token,'') IS NOT NULL
            )
            SELECT COUNT(DISTINCT claim_id)::int AS cnt FROM tokens WHERE doctor_key='sapna'
        """,
        'A_apr': """
            WITH tokens AS (
                SELECT c.id AS claim_id,
                       CASE WHEN token IN ('spana','drsapna') THEN 'sapna' ELSE token END AS doctor_key
                FROM claims c
                CROSS JOIN LATERAL unnest(string_to_array(regexp_replace(LOWER(COALESCE(c.assigned_doctor_id,'')), '[^a-z0-9,]+', '', 'g'), ',')) AS token
                WHERE c.status='completed'
                  AND c.updated_at IS NOT NULL
                  AND DATE(c.updated_at) >= DATE '2026-04-01'
                  AND DATE(c.updated_at) < DATE '2026-05-01'
                  AND NULLIF(token,'') IS NOT NULL
            )
            SELECT COUNT(DISTINCT claim_id)::int AS cnt FROM tokens WHERE doctor_key='sapna'
        """,
        'C_mar': """
            WITH latest_assignment AS (
                SELECT DISTINCT ON (claim_id) claim_id, DATE(occurred_at AT TIME ZONE 'Asia/Kolkata') AS allotment_date
                FROM workflow_events
                WHERE event_type='claim_assigned'
                ORDER BY claim_id, occurred_at DESC
            ),
            completed_claims AS (
                SELECT c.id AS claim_id, la.allotment_date,
                       CASE WHEN token IN ('spana','drsapna') THEN 'sapna' ELSE token END AS doctor_key
                FROM claims c
                LEFT JOIN latest_assignment la ON la.claim_id=c.id
                CROSS JOIN LATERAL unnest(string_to_array(regexp_replace(LOWER(COALESCE(c.assigned_doctor_id,'')), '[^a-z0-9,]+', '', 'g'), ',')) AS token
                WHERE c.status='completed' AND NULLIF(token,'') IS NOT NULL
            )
            SELECT COUNT(DISTINCT claim_id)::int AS cnt
            FROM completed_claims
            WHERE doctor_key='sapna' AND allotment_date >= DATE '2026-03-01' AND allotment_date < DATE '2026-04-01'
        """,
        'C_apr': """
            WITH latest_assignment AS (
                SELECT DISTINCT ON (claim_id) claim_id, DATE(occurred_at AT TIME ZONE 'Asia/Kolkata') AS allotment_date
                FROM workflow_events
                WHERE event_type='claim_assigned'
                ORDER BY claim_id, occurred_at DESC
            ),
            completed_claims AS (
                SELECT c.id AS claim_id, la.allotment_date,
                       CASE WHEN token IN ('spana','drsapna') THEN 'sapna' ELSE token END AS doctor_key
                FROM claims c
                LEFT JOIN latest_assignment la ON la.claim_id=c.id
                CROSS JOIN LATERAL unnest(string_to_array(regexp_replace(LOWER(COALESCE(c.assigned_doctor_id,'')), '[^a-z0-9,]+', '', 'g'), ',')) AS token
                WHERE c.status='completed' AND NULLIF(token,'') IS NOT NULL
            )
            SELECT COUNT(DISTINCT claim_id)::int AS cnt
            FROM completed_claims
            WHERE doctor_key='sapna' AND allotment_date >= DATE '2026-04-01' AND allotment_date < DATE '2026-05-01'
        """,
        'B_mar': """
            WITH events AS (
                SELECT we.claim_id,
                       CASE WHEN regexp_replace(LOWER(COALESCE(we.actor_id,'')), '[^a-z0-9]+', '', 'g') IN ('spana','drsapna') THEN 'sapna'
                            ELSE regexp_replace(LOWER(COALESCE(we.actor_id,'')), '[^a-z0-9]+', '', 'g') END AS doctor_key,
                       ROW_NUMBER() OVER (PARTITION BY we.claim_id ORDER BY we.occurred_at DESC, we.id DESC) AS rn
                FROM workflow_events we
                WHERE we.event_type='claim_status_updated'
                  AND COALESCE(we.event_payload->>'status','')='completed'
                  AND DATE(we.occurred_at AT TIME ZONE 'Asia/Kolkata') >= DATE '2026-03-01'
                  AND DATE(we.occurred_at AT TIME ZONE 'Asia/Kolkata') < DATE '2026-04-01'
            )
            SELECT COUNT(DISTINCT claim_id)::int AS cnt FROM events WHERE rn=1 AND doctor_key='sapna'
        """,
        'B_apr': """
            WITH events AS (
                SELECT we.claim_id,
                       CASE WHEN regexp_replace(LOWER(COALESCE(we.actor_id,'')), '[^a-z0-9]+', '', 'g') IN ('spana','drsapna') THEN 'sapna'
                            ELSE regexp_replace(LOWER(COALESCE(we.actor_id,'')), '[^a-z0-9]+', '', 'g') END AS doctor_key,
                       ROW_NUMBER() OVER (PARTITION BY we.claim_id ORDER BY we.occurred_at DESC, we.id DESC) AS rn
                FROM workflow_events we
                WHERE we.event_type='claim_status_updated'
                  AND COALESCE(we.event_payload->>'status','')='completed'
                  AND DATE(we.occurred_at AT TIME ZONE 'Asia/Kolkata') >= DATE '2026-04-01'
                  AND DATE(we.occurred_at AT TIME ZONE 'Asia/Kolkata') < DATE '2026-05-01'
            )
            SELECT COUNT(DISTINCT claim_id)::int AS cnt FROM events WHERE rn=1 AND doctor_key='sapna'
        """
    }
    for k, sql in queries.items():
        v = db.execute(text(sql)).mappings().first()['cnt']
        print(k, v)
finally:
    db.close()
