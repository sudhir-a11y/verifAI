from sqlalchemy import text
from app.db.session import SessionLocal

db = SessionLocal()
try:
    print('USERS')
    users = db.execute(text("""
        SELECT id, username, CAST(role AS TEXT) AS role, is_active
        FROM users
        WHERE LOWER(username) IN ('sapna','spana','drsapna')
        ORDER BY username
    """)).mappings().all()
    for u in users:
        print(dict(u))

    print('TOKENS_MAR_2026')
    rows = db.execute(text("""
        WITH completed_claim_tokens AS (
            SELECT c.id AS claim_id, token AS doctor_key
            FROM claims c
            CROSS JOIN LATERAL unnest(
                string_to_array(
                    regexp_replace(LOWER(COALESCE(c.assigned_doctor_id, '')), '[^a-z0-9,]+', '', 'g'),
                    ','
                )
            ) AS token
            WHERE c.status='completed'
              AND c.updated_at IS NOT NULL
              AND DATE(c.updated_at) >= DATE '2026-03-01'
              AND DATE(c.updated_at) < DATE '2026-04-01'
              AND NULLIF(token,'') IS NOT NULL
        )
        SELECT doctor_key, COUNT(DISTINCT claim_id) AS cnt
        FROM completed_claim_tokens
        WHERE doctor_key IN ('sapna','spana','drsapna')
        GROUP BY doctor_key
        ORDER BY doctor_key
    """)).mappings().all()
    for r in rows:
        print(dict(r))

    print('PAYMENT_ROWS_MAR_2026')
    ps_rows = db.execute(text("""
        WITH eligible_users AS (
            SELECT u.id AS user_id, u.username, CAST(u.role AS TEXT) AS role,
                   COALESCE(ubd.payment_rate, '') AS payment_rate_raw,
                   COALESCE(ubd.is_active, TRUE) AS bank_is_active
            FROM users u
            LEFT JOIN user_bank_details ubd ON ubd.user_id = u.id
            WHERE CAST(u.role AS TEXT) IN ('super_admin', 'doctor')
        ),
        completed_claim_tokens AS (
            SELECT c.id AS claim_id, token AS doctor_key
            FROM claims c
            CROSS JOIN LATERAL unnest(
                string_to_array(
                    regexp_replace(LOWER(COALESCE(c.assigned_doctor_id, '')), '[^a-z0-9,]+', '', 'g'),
                    ','
                )
            ) AS token
            WHERE c.status = 'completed'
              AND c.updated_at IS NOT NULL
              AND DATE(c.updated_at) >= DATE '2026-03-01'
              AND DATE(c.updated_at) < DATE '2026-04-01'
              AND NULLIF(token, '') IS NOT NULL
        ),
        completed_counts AS (
            SELECT ct.doctor_key, COUNT(DISTINCT ct.claim_id)::integer AS completed_cases
            FROM completed_claim_tokens ct
            GROUP BY ct.doctor_key
        )
        SELECT eu.user_id, eu.username, eu.role, eu.payment_rate_raw, COALESCE(cc.completed_cases,0) AS completed_cases
        FROM eligible_users eu
        LEFT JOIN completed_counts cc ON LOWER(eu.username) = cc.doctor_key
        WHERE LOWER(eu.username) IN ('sapna','spana','drsapna')
        ORDER BY LOWER(eu.username)
    """)).mappings().all()
    for r in ps_rows:
        print(dict(r))
finally:
    db.close()
