"""Repository for auth_logs table.

Audit logging — no business logic.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def log_auth_attempt(
    db: Session,
    *,
    legacy_auth_log_id: int | None,
    user_id: int | None,
    username: str,
    role: str,
    ip_address: str | None,
    user_agent: str | None,
    success: bool,
) -> None:
    """Insert an auth log entry. ON CONFLICT does nothing."""
    db.execute(
        text(
            """
            INSERT INTO auth_logs (legacy_auth_log_id, user_id, username, role, ip_address, user_agent, success)
            VALUES (:legacy_auth_log_id, :user_id, :username, :role, :ip_address, :user_agent, :success)
            ON CONFLICT (legacy_auth_log_id) DO NOTHING
            """
        ),
        {
            "legacy_auth_log_id": legacy_auth_log_id,
            "user_id": user_id,
            "username": username,
            "role": role,
            "ip_address": (ip_address or "")[:45] if ip_address else None,
            "user_agent": (user_agent or "")[:255] if user_agent else None,
            "success": success,
        },
    )
