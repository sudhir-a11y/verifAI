"""Repository for openai_claim_rule_suggestions table.

CRUD only — no business logic.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def list_rule_suggestions(
    db: Session,
    *,
    limit: int = 100,
    offset: int = 0,
    status_filter: str = "all",
) -> tuple[list[dict[str, Any]], int]:
    """List suggestions with status filter. Returns (rows, total_count)."""
    where = "WHERE status = :status" if status_filter != "all" else ""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if status_filter != "all":
        params["status"] = status_filter

    count_row = db.execute(text(f"SELECT COUNT(*) FROM openai_claim_rule_suggestions {where}"), params).first()
    total = int(count_row[0]) if count_row else 0

    rows = db.execute(
        text(
            f"""
            SELECT id, source_analysis_id, claim_id, suggestion_type, target_rule_id,
                   proposed_rule_id, suggested_name, suggested_decision,
                   suggested_conditions, suggested_remark_template,
                   suggested_required_evidence_json, source_context_text,
                   generator_confidence, generator_reasoning, status,
                   approved_rule_id, created_at, updated_at
            FROM openai_claim_rule_suggestions
            {where}
            ORDER BY (status = 'pending') DESC, created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()

    return [dict(r) for r in rows], total


def get_rule_suggestion_by_id(db: Session, suggestion_id: int) -> dict[str, Any] | None:
    """Get a single suggestion by id."""
    row = db.execute(
        text("SELECT * FROM openai_claim_rule_suggestions WHERE id = :id LIMIT 1"),
        {"id": suggestion_id},
    ).mappings().first()
    return dict(row) if row else None


def update_rule_suggestion_status(
    db: Session,
    suggestion_id: int,
    *,
    status: str,
    approved_rule_id: int | None,
    reviewed_by_user_id: int | None,
) -> dict[str, Any] | None:
    """Update suggestion status (approve/reject). Returns updated row or None."""
    row = db.execute(
        text(
            """
            UPDATE openai_claim_rule_suggestions
            SET status = :status,
                approved_rule_id = :approved_rule_id,
                reviewed_by_user_id = :reviewed_by_user_id,
                reviewed_at = NOW()
            WHERE id = :id
            RETURNING id, status, approved_rule_id
            """
        ),
        {
            "id": suggestion_id,
            "status": status,
            "approved_rule_id": approved_rule_id,
            "reviewed_by_user_id": reviewed_by_user_id,
        },
    ).mappings().first()
    return dict(row) if row else None
