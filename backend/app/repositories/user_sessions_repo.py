"""Repository for user_sessions table.

Session management — no business logic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def create_session(
    db: Session,
    *,
    user_id: int,
    token_hash: str,
    role_snapshot: str,
    expires_at: datetime,
) -> None:
    """Create a new user session."""
    db.execute(
        text(
            """
            INSERT INTO user_sessions (user_id, token_hash, role_snapshot, expires_at)
            VALUES (:user_id, :token_hash, :role_snapshot, :expires_at)
            """
        ),
        {
            "user_id": user_id,
            "token_hash": token_hash,
            "role_snapshot": role_snapshot,
            "expires_at": expires_at,
        },
    )


def get_user_by_token(db: Session, token_hash: str) -> dict[str, Any] | None:
    """Look up a user by session token. Returns None if expired/revoked."""
    row = db.execute(
        text(
            """
            SELECT u.id, u.username, u.role, u.is_active
            FROM user_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = :token_hash
              AND s.revoked_at IS NULL
              AND s.expires_at > NOW()
            LIMIT 1
            """
        ),
        {"token_hash": token_hash},
    ).mappings().first()
    return dict(row) if row else None


def revoke_session(db: Session, token_hash: str) -> None:
    """Revoke a session by token hash."""
    db.execute(
        text(
            """
            UPDATE user_sessions
            SET revoked_at = NOW()
            WHERE token_hash = :token_hash
              AND revoked_at IS NULL
            """
        ),
        {"token_hash": token_hash},
    )
