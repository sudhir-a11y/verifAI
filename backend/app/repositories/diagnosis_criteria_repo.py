"""Repository for openai_diagnosis_criteria table.

CRUD only — no business logic.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def list_diagnosis_criteria(
    db: Session,
    *,
    limit: int = 100,
    offset: int = 0,
    search: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """List criteria with optional search filter. Returns (rows, total_count)."""
    where = "WHERE diagnosis_name ILIKE :q OR criteria_id ILIKE :q" if search else ""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if search:
        params["q"] = f"%{search.strip()}%"

    count_row = db.execute(text(f"SELECT COUNT(*) FROM openai_diagnosis_criteria {where}"), params).first()
    total = int(count_row[0]) if count_row else 0

    rows = db.execute(
        text(
            f"""
            SELECT id, criteria_id, COALESCE(diagnosis_key,'') AS diagnosis_key,
                   diagnosis_name, aliases_json, required_evidence_json,
                   decision, COALESCE(remark_template,'') AS remark_template,
                   severity, priority, is_active, COALESCE(version,'1.0') AS version,
                   COALESCE(source,'manual') AS source, updated_at
            FROM openai_diagnosis_criteria
            {where}
            ORDER BY priority ASC, criteria_id ASC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()

    return [dict(r) for r in rows], total


def get_diagnosis_criteria_by_id(db: Session, criteria_id: int) -> dict[str, Any] | None:
    """Get a single criteria by its primary key id."""
    row = db.execute(
        text("SELECT * FROM openai_diagnosis_criteria WHERE id = :id LIMIT 1"),
        {"id": criteria_id},
    ).mappings().first()
    return dict(row) if row else None


def insert_diagnosis_criteria(db: Session, params: dict[str, Any]) -> int:
    """Insert new diagnosis criteria. Returns the new id."""
    row = db.execute(
        text(
            """
            INSERT INTO openai_diagnosis_criteria (
                criteria_id, diagnosis_key, diagnosis_name, aliases_json,
                required_evidence_json, decision, remark_template, severity,
                priority, is_active, version, source
            ) VALUES (
                :criteria_id, :diagnosis_key, :diagnosis_name, CAST(:aliases_json AS jsonb),
                CAST(:required_evidence_json AS jsonb), :decision, :remark_template, :severity,
                :priority, :is_active, :version, :source
            )
            RETURNING id
            """
        ),
        params,
    ).first()
    return int(row[0])


def update_diagnosis_criteria(db: Session, criteria_id: int, params: dict[str, Any]) -> int | None:
    """Update diagnosis criteria by id. Returns the id if found."""
    row = db.execute(
        text(
            """
            UPDATE openai_diagnosis_criteria
            SET criteria_id = :criteria_id,
                diagnosis_key = :diagnosis_key,
                diagnosis_name = :diagnosis_name,
                aliases_json = CAST(:aliases_json AS jsonb),
                required_evidence_json = CAST(:required_evidence_json AS jsonb),
                decision = :decision,
                remark_template = :remark_template,
                severity = :severity,
                priority = :priority,
                is_active = :is_active,
                version = :version,
                source = :source
            WHERE id = :id
            RETURNING id
            """
        ),
        {**params, "id": criteria_id},
    ).first()
    return int(row[0]) if row else None


def toggle_diagnosis_criteria_active(db: Session, criteria_id: int, is_active: bool) -> int | None:
    """Toggle is_active. Returns the id if found."""
    row = db.execute(
        text("UPDATE openai_diagnosis_criteria SET is_active = :is_active WHERE id = :id RETURNING id"),
        {"id": criteria_id, "is_active": is_active},
    ).first()
    return int(row[0]) if row else None


def delete_diagnosis_criteria(db: Session, criteria_id: int) -> bool:
    """Delete diagnosis criteria by id. Returns True if deleted."""
    result = db.execute(
        text("DELETE FROM openai_diagnosis_criteria WHERE id = :id"),
        {"id": criteria_id},
    )
    return bool(result.rowcount)


def load_active_diagnosis_criteria(db: Session) -> list[dict[str, Any]]:
    """Load all active diagnosis criteria for the checklist catalog."""
    rows = db.execute(
        text(
            """
            SELECT criteria_id, diagnosis_name, aliases_json, decision, remark_template, severity, priority, required_evidence_json
            FROM openai_diagnosis_criteria
            WHERE is_active = TRUE
            ORDER BY priority ASC, criteria_id ASC
            """
        ),
    ).mappings().all()
    return [dict(r) for r in rows]


def upsert_diagnosis_criteria_catalog(db: Session, params: dict[str, Any]) -> None:
    """Upsert diagnosis criteria from legacy sync."""
    db.execute(
        text(
            """
            INSERT INTO openai_diagnosis_criteria (
                criteria_id, diagnosis_name, diagnosis_key, aliases_json, decision,
                remark_template, severity, priority, required_evidence_json,
                is_active, updated_at, version, source
            ) VALUES (
                :criteria_id, :diagnosis_name, :diagnosis_key, CAST(:aliases_json AS jsonb), :decision,
                :remark_template, :severity, :priority, CAST(:required_evidence_json AS jsonb),
                TRUE, NOW(), :version, :source
            )
            ON CONFLICT (criteria_id)
            DO UPDATE SET
                diagnosis_name = EXCLUDED.diagnosis_name,
                diagnosis_key = EXCLUDED.diagnosis_key,
                aliases_json = EXCLUDED.aliases_json,
                decision = EXCLUDED.decision,
                remark_template = EXCLUDED.remark_template,
                severity = EXCLUDED.severity,
                priority = EXCLUDED.priority,
                required_evidence_json = EXCLUDED.required_evidence_json,
                is_active = TRUE,
                updated_at = NOW(),
                version = EXCLUDED.version,
                source = EXCLUDED.source
            """
        ),
        params,
    )
