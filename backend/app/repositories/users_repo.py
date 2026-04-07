"""Repository for users table.

User CRUD + auth lookups — no business logic.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_user_by_username(db: Session, username: str) -> dict[str, Any] | None:
    """Look up a user by normalized username."""
    row = db.execute(
        text(
            """
            SELECT id, username, password_hash, role, is_active
            FROM users
            WHERE REPLACE(LOWER(username), ' ', '') = :username_norm
            LIMIT 1
            """
        ),
        {"username_norm": username.lower().replace(" ", "")},
    ).mappings().first()
    return dict(row) if row else None


def get_user_by_id(db: Session, user_id: int) -> dict[str, Any] | None:
    """Get a user by id."""
    row = db.execute(
        text("SELECT id, username, role, is_active FROM users WHERE id = :user_id LIMIT 1"),
        {"user_id": user_id},
    ).mappings().first()
    return dict(row) if row else None


def get_user_hpr_id(db: Session, user_id: int) -> str | None:
    """Get the ABDM HPR ID for a user. Returns None if not set."""
    row = db.execute(
        text("SELECT abdm_hpr_id FROM users WHERE id = :user_id LIMIT 1"),
        {"user_id": user_id},
    ).mappings().first()
    if row is None:
        return None
    val = row.get("abdm_hpr_id")
    return str(val).strip() if val else None


def update_user_hpr_id(db: Session, user_id: int, hpr_id: str | None) -> None:
    """Update the ABDM HPR ID for a user."""
    db.execute(
        text("UPDATE users SET abdm_hpr_id = :hpr_id WHERE id = :user_id"),
        {"user_id": user_id, "hpr_id": hpr_id},
    )


def get_user_id_by_username(db: Session, username: str) -> int | None:
    """Get user id by username. Returns None if not found."""
    row = db.execute(
        text("SELECT id FROM users WHERE username = :username LIMIT 1"),
        {"username": username},
    ).mappings().first()
    return int(row["id"]) if row else None


def get_user_password_hash(db: Session, user_id: int) -> str | None:
    """Get the password hash for a user."""
    row = db.execute(
        text("SELECT id, password_hash FROM users WHERE id = :user_id LIMIT 1"),
        {"user_id": user_id},
    ).mappings().first()
    if row is None:
        return None
    return str(row.get("password_hash") or "")


def update_user_password(db: Session, user_id: int, password_hash: str) -> None:
    """Update a user's password hash."""
    db.execute(
        text("UPDATE users SET password_hash = :password_hash WHERE id = :user_id"),
        {"user_id": user_id, "password_hash": password_hash},
    )


def insert_user(db: Session, username: str, password_hash: str, role: str) -> dict[str, Any]:
    """Create a new user. Returns the new user row."""
    row = db.execute(
        text(
            """
            INSERT INTO users (username, password_hash, role, is_active)
            VALUES (:username, :password_hash, :role, TRUE)
            RETURNING id, username, role, is_active
            """
        ),
        {"username": username, "password_hash": password_hash, "role": role},
    ).mappings().one()
    return dict(row)


def count_users(db: Session) -> int:
    """Count total users."""
    row = db.execute(text("SELECT COUNT(*) FROM users")).first()
    return int(row[0]) if row else 0


def list_users(db: Session, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    """List users paginated."""
    rows = db.execute(
        text(
            """
            SELECT id, username, role, is_active
            FROM users
            ORDER BY username ASC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"limit": limit, "offset": offset},
    ).mappings().all()
    return [dict(r) for r in rows]


def update_user_role(db: Session, user_id: int, role: str) -> None:
    """Update a user's role and set is_active to TRUE."""
    db.execute(
        text("UPDATE users SET role = :role, is_active = TRUE WHERE id = :id"),
        {"role": role, "id": user_id},
    )


def list_doctor_usernames(db: Session) -> list[str]:
    """List all active doctor and super_admin usernames."""
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
