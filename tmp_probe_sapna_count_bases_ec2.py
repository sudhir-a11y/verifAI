from sqlalchemy import text
from app.db.session import SessionLocal

def q(db, sql, params=None):
    return db.execute(text(sql), params or {}).mappings().all()

db = SessionLocal()
try:
    months = [('2026-03-01','2026-04-01','2026-03'),('2026-04-01','2026-05-01','2026-04')]

    print('USER_ROWS')
    rows = q(db, """
        SELECT id, username, CAST(role AS TEXT) AS role
        FROM users
        WHERE LOWER(username) IN ('sapna','spana','drsapna')
        ORDER BY username
    """)
    for r in rows:
        print(dict(r))

    for start, end, m in months:
        print('--- MONTH', m)

        # A) claims.status=completed + updated_at month + assigned_doctor_id token sapna aliases
        rows = q(db, """
            WITH tokens AS (
                SELECT c.id AS claim_id,
                       CASE WHEN token IN ('spana','drsapna') THEN 'sapna' ELSE token END AS doctor_key
                FROM claims c
                CROSS JOIN LATERAL unnest(
                    string_to_array(regexp_replace(LOWER(COALESCE(c.assigned_doctor_id,'')), '[^a-z0-9,]+', '', 'g'), ',')
                ) AS token
                WHERE c.status='completed'
                  AND c.updated_at IS NOT NULL
                  AND DATE(c.updated_at) >= DATE :start
                  AND DATE(c.updated_at) < DATE :end
                  AND NULLIF(token,'') IS NOT NULL
            )
            SELECT COUNT(DISTINCT claim_id)::int AS cnt
            FROM tokens
            WHERE doctor_key='sapna'
        """, {'start': start, 'end': end})
        print('A_updated_at_assigned_token', rows[0]['cnt'])

        # B) workflow claim_status_updated completed by actor_id month (IST), dedup claim
        rows = q(db, """
            WITH events AS (
                SELECT we.claim_id,
                       CASE WHEN regexp_replace(LOWER(COALESCE(we.actor_id,'')), '[^a-z0-9]+', '', 'g') IN ('spana','drsapna') THEN 'sapna'
                            ELSE regexp_replace(LOWER(COALESCE(we.actor_id,'')), '[^a-z0-9]+', '', 'g') END AS doctor_key,
                       ROW_NUMBER() OVER (PARTITION BY we.claim_id ORDER BY we.occurred_at DESC, we.id DESC) AS rn
                FROM workflow_events we
                WHERE we.event_type='claim_status_updated'
                  AND COALESCE(we.event_payload->>'status','')='completed'
                  AND DATE(we.occurred_at AT TIME ZONE 'Asia/Kolkata') >= DATE :start
                  AND DATE(we.occurred_at AT TIME ZONE 'Asia/Kolkata') < DATE :end
            )
            SELECT COUNT(DISTINCT claim_id)::int AS cnt
            FROM events
            WHERE rn=1 AND doctor_key='sapna'
        """, {'start': start, 'end': end})
        print('B_status_event_actor_month', rows[0]['cnt'])

        # C) allotment_date month + assigned_doctor_id token
        rows = q(db, """
            WITH latest_assignment AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    DATE(occurred_at AT TIME ZONE 'Asia/Kolkata') AS allotment_date
                FROM workflow_events
                WHERE event_type='claim_assigned'
                ORDER BY claim_id, occurred_at DESC
            ),
            completed_claims AS (
                SELECT c.id AS claim_id, la.allotment_date,
                       CASE WHEN token IN ('spana','drsapna') THEN 'sapna' ELSE token END AS doctor_key
                FROM claims c
                LEFT JOIN latest_assignment la ON la.claim_id=c.id
                CROSS JOIN LATERAL unnest(
                    string_to_array(regexp_replace(LOWER(COALESCE(c.assigned_doctor_id,'')), '[^a-z0-9,]+', '', 'g'), ',')
                ) AS token
                WHERE c.status='completed'
                  AND NULLIF(token,'') IS NOT NULL
            )
            SELECT COUNT(DISTINCT claim_id)::int AS cnt
            FROM completed_claims
            WHERE doctor_key='sapna'
              AND allotment_date >= DATE :start
              AND allotment_date < DATE :end
        """, {'start': start, 'end': end})
        print('C_allotment_assigned_token', rows[0]['cnt'])

    # Combined Mar+Apr by updated_at+assigned token
    rows = q(db, """
        WITH tokens AS (
            SELECT c.id AS claim_id,
                   CASE WHEN token IN ('spana','drsapna') THEN 'sapna' ELSE token END AS doctor_key
            FROM claims c
            CROSS JOIN LATERAL unnest(
                string_to_array(regexp_replace(LOWER(COALESCE(c.assigned_doctor_id,'')), '[^a-z0-9,]+', '', 'g'), ',')
            ) AS token
            WHERE c.status='completed'
              AND c.updated_at IS NOT NULL
              AND DATE(c.updated_at) >= DATE '2026-03-01'
              AND DATE(c.updated_at) < DATE '2026-05-01'
              AND NULLIF(token,'') IS NOT NULL
        )
        SELECT COUNT(DISTINCT claim_id)::int AS cnt
        FROM tokens
        WHERE doctor_key='sapna'
    """)
    print('MAR_APR_UPDATED_AT_ASSIGNED_TOKEN', rows[0]['cnt'])
finally:
    db.close()
