from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def ensure_user_bank_details_table(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS user_bank_details (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                account_holder_name VARCHAR(255) NOT NULL DEFAULT '',
                bank_name VARCHAR(255) NOT NULL DEFAULT '',
                branch_name VARCHAR(255) NOT NULL DEFAULT '',
                account_number VARCHAR(64) NOT NULL DEFAULT '',
                payment_rate VARCHAR(64) NOT NULL DEFAULT '',
                ifsc_code VARCHAR(32) NOT NULL DEFAULT '',
                upi_id VARCHAR(255) NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_by VARCHAR(100) NOT NULL DEFAULT '',
                updated_by VARCHAR(100) NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    db.execute(
        text("ALTER TABLE user_bank_details ADD COLUMN IF NOT EXISTS payment_rate VARCHAR(64) NOT NULL DEFAULT ''")
    )
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_user_bank_details_user_id ON user_bank_details(user_id)"))


def list_payment_sheet_rows(
    db: Session,
    *,
    month_start,
    month_end,
) -> list[dict]:
    rows = db.execute(
        text(
            """
            WITH eligible_users AS (
                SELECT
                    u.id AS user_id,
                    u.username,
                    CAST(u.role AS TEXT) AS role,
                    COALESCE(ubd.payment_rate, '') AS payment_rate_raw,
                    COALESCE(ubd.is_active, TRUE) AS bank_is_active
                FROM users u
                LEFT JOIN user_bank_details ubd ON ubd.user_id = u.id
                WHERE CAST(u.role AS TEXT) IN ('super_admin', 'doctor')
            ),
            completed_claim_tokens AS (
                SELECT
                    c.id AS claim_id,
                    token AS doctor_key
                FROM claims c
                CROSS JOIN LATERAL unnest(
                    string_to_array(
                        regexp_replace(LOWER(COALESCE(c.assigned_doctor_id, '')), '[^a-z0-9,]+', '', 'g'),
                        ','
                    )
                ) AS token
                WHERE c.status = 'completed'
                  AND COALESCE(c.completed_at, c.updated_at) IS NOT NULL
                  AND DATE(COALESCE(c.completed_at, c.updated_at) AT TIME ZONE 'Asia/Kolkata') >= :month_start
                  AND DATE(COALESCE(c.completed_at, c.updated_at) AT TIME ZONE 'Asia/Kolkata') < :month_end
                  AND NULLIF(token, '') IS NOT NULL
            ),
            completed_counts AS (
                SELECT
                    ct.doctor_key,
                    COUNT(DISTINCT ct.claim_id)::integer AS completed_cases
                FROM completed_claim_tokens ct
                GROUP BY ct.doctor_key
            )
            SELECT
                eu.user_id,
                eu.username,
                eu.role,
                eu.payment_rate_raw,
                eu.bank_is_active,
                COALESCE(cc.completed_cases, 0)::integer AS completed_cases
            FROM eligible_users eu
            LEFT JOIN completed_counts cc ON LOWER(eu.username) = cc.doctor_key
            ORDER BY LOWER(eu.username) ASC
            """
        ),
        {"month_start": month_start, "month_end": month_end},
    ).mappings().all()
    return [dict(row) for row in rows]

