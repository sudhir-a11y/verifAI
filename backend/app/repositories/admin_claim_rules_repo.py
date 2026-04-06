from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def count_claim_rules(db: Session, *, search: str | None) -> int:
    where = ""
    params: dict[str, Any] = {}
    if search and str(search).strip():
        where = "WHERE rule_id ILIKE :q OR name ILIKE :q"
        params["q"] = f"%{str(search).strip()}%"
    total = db.execute(text(f"SELECT COUNT(*) FROM openai_claim_rules {where}"), params).scalar_one()
    return int(total or 0)


def list_claim_rules(
    db: Session,
    *,
    search: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    where = ""
    params: dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
    if search and str(search).strip():
        where = "WHERE rule_id ILIKE :q OR name ILIKE :q"
        params["q"] = f"%{str(search).strip()}%"

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

    return [dict(row) for row in rows]


def insert_claim_rule(
    db: Session,
    *,
    rule_id: str,
    name: str,
    scope: list[str],
    conditions: str,
    decision: str,
    remark_template: str,
    required_evidence: list[str],
    severity: str,
    priority: int,
    is_active: bool,
    version: str,
    source: str,
) -> int:
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
        {
            "rule_id": rule_id,
            "name": name,
            "scope_json": json.dumps(scope),
            "conditions": conditions,
            "decision": decision,
            "remark_template": remark_template,
            "required_evidence_json": json.dumps(required_evidence),
            "severity": severity,
            "priority": int(priority),
            "is_active": bool(is_active),
            "version": version,
            "source": source,
        },
    ).mappings().one()
    return int(row["id"])


def update_claim_rule(
    db: Session,
    *,
    row_id: int,
    rule_id: str,
    name: str,
    scope: list[str],
    conditions: str,
    decision: str,
    remark_template: str,
    required_evidence: list[str],
    severity: str,
    priority: int,
    is_active: bool,
    version: str,
    source: str,
) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            UPDATE openai_claim_rules
            SET rule_id = :rule_id,
                name = :name,
                scope_json = CAST(:scope_json AS jsonb),
                conditions = :conditions,
                decision = :decision,
                remark_template = :remark_template,
                required_evidence_json = CAST(:required_evidence_json AS jsonb),
                severity = :severity,
                priority = :priority,
                is_active = :is_active,
                version = :version,
                source = :source,
                updated_at = NOW()
            WHERE id = :id
            RETURNING id, rule_id, name, scope_json, COALESCE(conditions,'') AS conditions,
                      decision, COALESCE(remark_template,'') AS remark_template,
                      required_evidence_json, severity, priority, is_active,
                      COALESCE(version,'1.0') AS version,
                      COALESCE(source,'manual') AS source,
                      updated_at
            """
        ),
        {
            "id": int(row_id),
            "rule_id": rule_id,
            "name": name,
            "scope_json": json.dumps(scope),
            "conditions": conditions,
            "decision": decision,
            "remark_template": remark_template,
            "required_evidence_json": json.dumps(required_evidence),
            "severity": severity,
            "priority": int(priority),
            "is_active": bool(is_active),
            "version": version,
            "source": source,
        },
    ).mappings().first()
    return dict(row) if row is not None else None


def set_claim_rule_active(db: Session, *, row_id: int, is_active: bool) -> bool:
    row = db.execute(
        text("UPDATE openai_claim_rules SET is_active = :is_active WHERE id = :id RETURNING id"),
        {"id": int(row_id), "is_active": bool(is_active)},
    ).mappings().first()
    return row is not None


def delete_claim_rule(db: Session, *, row_id: int) -> bool:
    deleted = db.execute(text("DELETE FROM openai_claim_rules WHERE id = :id"), {"id": int(row_id)}).rowcount
    return bool(deleted)


def next_claim_rule_id(db: Session) -> str:
    rows = db.execute(text("SELECT rule_id FROM openai_claim_rules WHERE rule_id ILIKE 'R%'"))
    max_no = 0
    for row in rows:
        rule_id = str(row[0] or "").strip().upper()
        if rule_id.startswith("R") and rule_id[1:].isdigit():
            max_no = max(max_no, int(rule_id[1:]))
    return f"R{max_no + 1:04d}"


def claim_rule_id_exists(db: Session, *, rule_id: str) -> bool:
    existing = db.execute(
        text("SELECT 1 FROM openai_claim_rules WHERE rule_id = :rule_id LIMIT 1"),
        {"rule_id": str(rule_id or "").strip().upper()},
    ).first()
    return existing is not None


def claim_rule_exists_by_rule_id(db: Session, *, rule_id: str) -> bool:
    existing = db.execute(
        text("SELECT id FROM openai_claim_rules WHERE rule_id = :rule_id LIMIT 1"),
        {"rule_id": str(rule_id or "").strip().upper()},
    ).mappings().first()
    return existing is not None


def update_claim_rule_by_rule_id_for_suggestion(
    db: Session,
    *,
    rule_id: str,
    name: str,
    conditions: str,
    decision: str,
    remark_template: str,
    required_evidence: list[str],
    severity: str,
    source: str,
) -> None:
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
                source = :source
            WHERE rule_id = :rule_id
            """
        ),
        {
            "rule_id": str(rule_id or "").strip().upper(),
            "name": name,
            "conditions": conditions,
            "decision": decision,
            "remark_template": remark_template,
            "required_evidence_json": json.dumps(required_evidence),
            "severity": severity,
            "source": source,
        },
    )


def upsert_claim_rule_for_suggestion(
    db: Session,
    *,
    rule_id: str,
    name: str,
    conditions: str,
    decision: str,
    remark_template: str,
    required_evidence: list[str],
    severity: str,
    source: str,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO openai_claim_rules (
                rule_id, name, scope_json, conditions, decision, remark_template,
                required_evidence_json, severity, priority, is_active, version, source
            ) VALUES (
                :rule_id, :name, CAST(:scope_json AS jsonb), :conditions, :decision, :remark_template,
                CAST(:required_evidence_json AS jsonb), :severity, 999, TRUE, '1.0', :source
            )
            ON CONFLICT (rule_id) DO UPDATE
            SET name = EXCLUDED.name,
                conditions = EXCLUDED.conditions,
                decision = EXCLUDED.decision,
                remark_template = EXCLUDED.remark_template,
                required_evidence_json = EXCLUDED.required_evidence_json,
                severity = EXCLUDED.severity,
                source = EXCLUDED.source
            """
        ),
        {
            "rule_id": str(rule_id or "").strip().upper(),
            "name": name,
            "scope_json": json.dumps([]),
            "conditions": conditions,
            "decision": decision,
            "remark_template": remark_template,
            "required_evidence_json": json.dumps(required_evidence),
            "severity": severity,
            "source": source,
        },
    )
