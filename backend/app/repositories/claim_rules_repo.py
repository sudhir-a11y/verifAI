"""Repository for openai_claim_rules table.

CRUD only — no business logic.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def list_claim_rules(
    db: Session,
    *,
    limit: int = 100,
    offset: int = 0,
    search: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """List rules with optional search filter. Returns (rows, total_count)."""
    where = "WHERE name ILIKE :q OR rule_id ILIKE :q OR conditions ILIKE :q" if search else ""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if search:
        params["q"] = f"%{search.strip()}%"

    count_row = db.execute(text(f"SELECT COUNT(*) FROM openai_claim_rules {where}"), params).first()
    total = int(count_row[0]) if count_row else 0

    rows = db.execute(
        text(
            f"""
            SELECT id, rule_id, name, scope_json, COALESCE(conditions,'') AS conditions,
                   decision, COALESCE(remark_template,'') AS remark_template,
                   required_evidence_json, severity, priority, is_active,
                   COALESCE(version,'1.0') AS version,
                   COALESCE(source,'manual') AS source,
                   updated_at
            FROM openai_claim_rules
            {where}
            ORDER BY priority ASC, rule_id ASC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()

    return [dict(r) for r in rows], total


def get_claim_rule_by_id(db: Session, rule_id: int) -> dict[str, Any] | None:
    """Get a single rule by its primary key id."""
    row = db.execute(
        text("SELECT * FROM openai_claim_rules WHERE id = :id LIMIT 1"),
        {"id": rule_id},
    ).mappings().first()
    return dict(row) if row else None


def get_claim_rule_by_rule_id(db: Session, rule_id: str) -> dict[str, Any] | None:
    """Get a single rule by its business rule_id."""
    row = db.execute(
        text("SELECT id FROM openai_claim_rules WHERE rule_id = :rule_id LIMIT 1"),
        {"rule_id": rule_id},
    ).mappings().first()
    return dict(row) if row else None


def claim_rule_exists_by_rule_id(db: Session, rule_id: str) -> bool:
    """Check if a rule exists by its business rule_id."""
    row = db.execute(
        text("SELECT 1 FROM openai_claim_rules WHERE rule_id = :rule_id LIMIT 1"),
        {"rule_id": rule_id},
    ).first()
    return row is not None


def insert_claim_rule(db: Session, params: dict[str, Any]) -> int:
    """Insert a new claim rule. Returns the new id."""
    row = db.execute(
        text(
            """
            INSERT INTO openai_claim_rules (
                rule_id, name, scope_json, conditions, decision,
                remark_template, required_evidence_json, severity,
                priority, is_active, version, source
            ) VALUES (
                :rule_id, :name, CAST(:scope_json AS jsonb), :conditions, :decision,
                :remark_template, CAST(:required_evidence_json AS jsonb), :severity,
                :priority, :is_active, :version, :source
            )
            RETURNING id
            """
        ),
        params,
    ).first()
    return int(row[0])


def update_claim_rule(db: Session, rule_id: int, params: dict[str, Any]) -> int | None:
    """Update a claim rule by id. Returns the id if found, None otherwise."""
    row = db.execute(
        text(
            """
            UPDATE openai_claim_rules
            SET rule_id = :rule_id,
                scope_json = CAST(:scope_json AS jsonb),
                conditions = :conditions,
                decision = :decision,
                remark_template = :remark_template,
                required_evidence_json = CAST(:required_evidence_json AS jsonb),
                severity = :severity,
                priority = :priority,
                is_active = :is_active,
                version = :version,
                source = :source
            WHERE id = :id
            RETURNING id
            """
        ),
        {**params, "id": rule_id},
    ).first()
    return int(row[0]) if row else None


def toggle_claim_rule_active(db: Session, rule_id: int, is_active: bool) -> int | None:
    """Toggle is_active for a rule. Returns the id if found."""
    row = db.execute(
        text("UPDATE openai_claim_rules SET is_active = :is_active WHERE id = :id RETURNING id"),
        {"id": rule_id, "is_active": is_active},
    ).first()
    return int(row[0]) if row else None


def delete_claim_rule(db: Session, rule_id: int) -> bool:
    """Delete a claim rule by id. Returns True if deleted."""
    result = db.execute(
        text("DELETE FROM openai_claim_rules WHERE id = :id"),
        {"id": rule_id},
    )
    return bool(result.rowcount)


def get_next_rule_id(db: Session) -> str:
    """Generate the next available rule_id (R###)."""
    rows = db.execute(
        text("SELECT rule_id FROM openai_claim_rules WHERE rule_id ILIKE 'R%'"),
    ).mappings().all()
    max_num = 0
    for row in rows:
        rid = str(row.get("rule_id") or "")
        if rid.startswith("R"):
            try:
                num = int(rid[1:])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"R{max_num + 1:03d}"


def upsert_claim_rule_from_suggestion(db: Session, params: dict[str, Any]) -> int:
    """Insert or update a claim rule from a suggestion (ON CONFLICT)."""
    row = db.execute(
        text(
            """
            INSERT INTO openai_claim_rules (
                rule_id, name, scope_json, conditions, decision, remark_template,
                required_evidence_json, severity, priority, is_active, version, source
            ) VALUES (
                :rule_id, :name, CAST(:scope_json AS jsonb), :conditions, :decision, :remark_template,
                CAST(:required_evidence_json AS jsonb), :severity, 999, TRUE, '1.0', 'suggested'
            )
            ON CONFLICT (rule_id) DO UPDATE
            SET name = EXCLUDED.name,
                conditions = EXCLUDED.conditions,
                decision = EXCLUDED.decision,
                remark_template = EXCLUDED.remark_template,
                required_evidence_json = EXCLUDED.required_evidence_json,
                severity = EXCLUDED.severity,
                source = EXCLUDED.source
            RETURNING id
            """
        ),
        params,
    ).first()
    return int(row[0])


def update_claim_rule_from_suggestion(db: Session, rule_id: str, params: dict[str, Any]) -> None:
    """Update an existing rule from a suggestion."""
    db.execute(
        text(
            """
            UPDATE openai_claim_rules
            SET name = :name,
                conditions = :conditions,
                decision = :decision,
                remark_template = :remark_template,
                required_evidence_json = CAST(:required_evidence_json AS jsonb),
                severity = :severity,
                source = 'suggested_update'
            WHERE rule_id = :rule_id
            """
        ),
        {**params, "rule_id": rule_id},
    )


def load_active_claim_rules(db: Session) -> list[dict[str, Any]]:
    """Load all active claim rules for the checklist catalog."""
    rows = db.execute(
        text(
            """
            SELECT rule_id, name, scope_json, conditions, decision, remark_template, severity, priority, required_evidence_json
            FROM openai_claim_rules
            WHERE is_active = TRUE
            ORDER BY priority ASC, rule_id ASC
            """
        ),
    ).mappings().all()
    return [dict(r) for r in rows]


def upsert_claim_rule_catalog(db: Session, params: dict[str, Any]) -> None:
    """Upsert a claim rule from legacy sync."""
    db.execute(
        text(
            """
            INSERT INTO openai_claim_rules (
                rule_id, name, scope_json, conditions, decision, remark_template,
                severity, priority, required_evidence_json, is_active, updated_at,
                version, source
            ) VALUES (
                :rule_id, :name, CAST(:scope_json AS jsonb), :conditions, :decision, :remark_template,
                :severity, :priority, CAST(:required_evidence_json AS jsonb), TRUE, NOW(),
                :version, :source
            )
            ON CONFLICT (rule_id)
            DO UPDATE SET
                name = EXCLUDED.name,
                scope_json = EXCLUDED.scope_json,
                conditions = EXCLUDED.conditions,
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
