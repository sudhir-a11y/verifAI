from sqlalchemy import text
from sqlalchemy.orm import Session


def get_user_row_by_id(db: Session, *, user_id: int) -> dict | None:
    row = db.execute(
        text("SELECT id, username, CAST(role AS TEXT) AS role, is_active FROM users WHERE id = :user_id LIMIT 1"),
        {"user_id": int(user_id)},
    ).mappings().first()
    return dict(row) if row is not None else None


def list_doctor_usernames(db: Session) -> list[str]:
    rows = db.execute(
        text(
            """
            WITH user_doctors AS (
                SELECT LOWER(TRIM(username)) AS username
                FROM users
                WHERE is_active = TRUE
                  AND role IN ('doctor', 'super_admin')
                  AND NULLIF(TRIM(username), '') IS NOT NULL
            ),
            assigned_doctors AS (
                SELECT LOWER(TRIM(doctor_token)) AS username
                FROM claims c
                CROSS JOIN LATERAL UNNEST(
                    string_to_array(REPLACE(COALESCE(c.assigned_doctor_id, ''), ' ', ''), ',')
                ) AS doctor_token
                WHERE NULLIF(TRIM(doctor_token), '') IS NOT NULL
            )
            SELECT DISTINCT username
            FROM (
                SELECT username FROM user_doctors
                UNION ALL
                SELECT username FROM assigned_doctors
            ) merged
            WHERE NULLIF(TRIM(username), '') IS NOT NULL
            ORDER BY username ASC
            """
        )
    ).mappings().all()
    return [str(r.get("username") or "").strip() for r in rows if str(r.get("username") or "").strip()]

