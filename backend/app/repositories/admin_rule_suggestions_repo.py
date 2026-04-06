from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def count_rule_suggestions(db: Session, *, status_filter: str) -> int:
    where = ""
    params: dict[str, Any] = {}
    if status_filter != "all":
        where = "WHERE status = :status"
        params["status"] = status_filter
    total = db.execute(text(f"SELECT COUNT(*) FROM openai_claim_rule_suggestions {where}"), params).scalar_one()
    return int(total or 0)


def list_rule_suggestions(
    db: Session,
    *,
    status_filter: str,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    where = ""
    params: dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
    if status_filter != "all":
        where = "WHERE status = :status"
        params["status"] = status_filter

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
    return [dict(row) for row in rows]


def get_rule_suggestion(db: Session, *, suggestion_id: int) -> dict[str, Any] | None:
    row = db.execute(
        text("SELECT * FROM openai_claim_rule_suggestions WHERE id = :id LIMIT 1"),
        {"id": int(suggestion_id)},
    ).mappings().first()
    return dict(row) if row is not None else None


def update_rule_suggestion_status(
    db: Session,
    *,
    suggestion_id: int,
    status: str,
    approved_rule_id: str,
    reviewed_by_username: str,
) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            UPDATE openai_claim_rule_suggestions
            SET status = :status,
                approved_rule_id = :approved_rule_id,
                reviewed_by_user_id = (SELECT id FROM users WHERE username = :username LIMIT 1),
                reviewed_at = NOW(),
                updated_at = NOW()
            WHERE id = :id
            RETURNING id, status, approved_rule_id, updated_at
            """
        ),
        {
            "id": int(suggestion_id),
            "status": status,
            "approved_rule_id": approved_rule_id,
            "username": reviewed_by_username,
        },
    ).mappings().first()
    return dict(row) if row is not None else None
