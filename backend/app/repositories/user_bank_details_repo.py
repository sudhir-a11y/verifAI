from typing import Any

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
        text(
            "ALTER TABLE user_bank_details ADD COLUMN IF NOT EXISTS payment_rate VARCHAR(64) NOT NULL DEFAULT ''"
        )
    )
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_user_bank_details_user_id ON user_bank_details(user_id)"))


def count_user_bank_details(db: Session, *, search: str) -> int:
    return int(
        db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM users u
                LEFT JOIN user_bank_details ubd ON ubd.user_id = u.id
                WHERE CAST(u.role AS TEXT) IN ('super_admin', 'doctor')
                  AND (
                       :search = ''
                    OR LOWER(u.username) LIKE :search
                    OR LOWER(CAST(u.role AS TEXT)) LIKE :search
                    OR LOWER(COALESCE(ubd.account_holder_name, '')) LIKE :search
                    OR LOWER(COALESCE(ubd.bank_name, '')) LIKE :search
                    OR LOWER(COALESCE(ubd.branch_name, '')) LIKE :search
                    OR LOWER(COALESCE(ubd.account_number, '')) LIKE :search
                    OR LOWER(COALESCE(ubd.payment_rate, '')) LIKE :search
                    OR LOWER(COALESCE(ubd.ifsc_code, '')) LIKE :search
                    OR LOWER(COALESCE(ubd.upi_id, '')) LIKE :search
                    OR LOWER(COALESCE(ubd.notes, '')) LIKE :search
                  )
                """
            ),
            {"search": search},
        ).scalar_one()
    )


def list_user_bank_details_rows(
    db: Session,
    *,
    search: str,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT
                u.id AS user_id,
                u.username,
                CAST(u.role AS TEXT) AS role,
                u.is_active AS user_is_active,
                COALESCE(ubd.account_holder_name, '') AS account_holder_name,
                COALESCE(ubd.bank_name, '') AS bank_name,
                COALESCE(ubd.branch_name, '') AS branch_name,
                COALESCE(ubd.account_number, '') AS account_number,
                COALESCE(ubd.payment_rate, '') AS payment_rate,
                COALESCE(ubd.ifsc_code, '') AS ifsc_code,
                COALESCE(ubd.upi_id, '') AS upi_id,
                COALESCE(ubd.notes, '') AS notes,
                COALESCE(ubd.is_active, TRUE) AS bank_is_active,
                COALESCE(ubd.updated_by, '') AS updated_by,
                ubd.updated_at AS updated_at
            FROM users u
                LEFT JOIN user_bank_details ubd ON ubd.user_id = u.id
                WHERE CAST(u.role AS TEXT) IN ('super_admin', 'doctor')
                  AND (
                       :search = ''
                    OR LOWER(u.username) LIKE :search
                    OR LOWER(CAST(u.role AS TEXT)) LIKE :search
                    OR LOWER(COALESCE(ubd.account_holder_name, '')) LIKE :search
                    OR LOWER(COALESCE(ubd.bank_name, '')) LIKE :search
                    OR LOWER(COALESCE(ubd.branch_name, '')) LIKE :search
                    OR LOWER(COALESCE(ubd.account_number, '')) LIKE :search
                    OR LOWER(COALESCE(ubd.payment_rate, '')) LIKE :search
                    OR LOWER(COALESCE(ubd.ifsc_code, '')) LIKE :search
                    OR LOWER(COALESCE(ubd.upi_id, '')) LIKE :search
                    OR LOWER(COALESCE(ubd.notes, '')) LIKE :search
                  )
            ORDER BY LOWER(u.username) ASC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"search": search, "limit": int(limit), "offset": int(offset)},
    ).mappings().all()
    return [dict(r) for r in rows]


def upsert_user_bank_details(
    db: Session,
    *,
    user_id: int,
    account_holder_name: str,
    bank_name: str,
    branch_name: str,
    account_number: str,
    payment_rate: str,
    ifsc_code: str,
    upi_id: str,
    notes: str,
    is_active: bool,
    actor: str,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO user_bank_details (
                user_id,
                account_holder_name,
                bank_name,
                branch_name,
                account_number,
                payment_rate,
                ifsc_code,
                upi_id,
                notes,
                is_active,
                created_by,
                updated_by
            )
            VALUES (
                :user_id,
                :account_holder_name,
                :bank_name,
                :branch_name,
                :account_number,
                :payment_rate,
                :ifsc_code,
                :upi_id,
                :notes,
                :is_active,
                :actor,
                :actor
            )
            ON CONFLICT (user_id)
            DO UPDATE SET
                account_holder_name = EXCLUDED.account_holder_name,
                bank_name = EXCLUDED.bank_name,
                branch_name = EXCLUDED.branch_name,
                account_number = EXCLUDED.account_number,
                payment_rate = EXCLUDED.payment_rate,
                ifsc_code = EXCLUDED.ifsc_code,
                upi_id = EXCLUDED.upi_id,
                notes = EXCLUDED.notes,
                is_active = EXCLUDED.is_active,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            """
        ),
        {
            "user_id": int(user_id),
            "account_holder_name": account_holder_name,
            "bank_name": bank_name,
            "branch_name": branch_name,
            "account_number": account_number,
            "payment_rate": payment_rate,
            "ifsc_code": ifsc_code,
            "upi_id": upi_id,
            "notes": notes,
            "is_active": bool(is_active),
            "actor": actor,
        },
    )


def get_user_bank_details_row(db: Session, *, user_id: int) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT
                u.id AS user_id,
                u.username,
                CAST(u.role AS TEXT) AS role,
                u.is_active AS user_is_active,
                COALESCE(ubd.account_holder_name, '') AS account_holder_name,
                COALESCE(ubd.bank_name, '') AS bank_name,
                COALESCE(ubd.branch_name, '') AS branch_name,
                COALESCE(ubd.account_number, '') AS account_number,
                COALESCE(ubd.payment_rate, '') AS payment_rate,
                COALESCE(ubd.ifsc_code, '') AS ifsc_code,
                COALESCE(ubd.upi_id, '') AS upi_id,
                COALESCE(ubd.notes, '') AS notes,
                COALESCE(ubd.is_active, TRUE) AS bank_is_active,
                COALESCE(ubd.updated_by, '') AS updated_by,
                ubd.updated_at AS updated_at
            FROM users u
            LEFT JOIN user_bank_details ubd ON ubd.user_id = u.id
            WHERE u.id = :user_id
            LIMIT 1
            """
        ),
        {"user_id": int(user_id)},
    ).mappings().first()
    return dict(row) if row is not None else None

