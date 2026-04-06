from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def count_diagnosis_criteria(db: Session, *, search: str | None) -> int:
    where = ""
    params: dict[str, Any] = {}
    if search and str(search).strip():
        where = "WHERE criteria_id ILIKE :q OR diagnosis_name ILIKE :q OR diagnosis_key ILIKE :q"
        params["q"] = f"%{str(search).strip()}%"
    total = db.execute(text(f"SELECT COUNT(*) FROM openai_diagnosis_criteria {where}"), params).scalar_one()
    return int(total or 0)


def list_diagnosis_criteria(
    db: Session,
    *,
    search: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    where = ""
    params: dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
    if search and str(search).strip():
        where = "WHERE criteria_id ILIKE :q OR diagnosis_name ILIKE :q OR diagnosis_key ILIKE :q"
        params["q"] = f"%{str(search).strip()}%"

    rows = db.execute(
        text(
            f"""
            SELECT id, criteria_id, diagnosis_key, diagnosis_name, aliases_json,
                   required_evidence_json, decision,
                   COALESCE(remark_template,'') AS remark_template,
                   severity, priority, is_active,
                   COALESCE(version,'1.0') AS version,
                   COALESCE(source,'manual') AS source,
                   updated_at
            FROM openai_diagnosis_criteria
            {where}
            ORDER BY priority ASC, criteria_id ASC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()
    return [dict(row) for row in rows]


def insert_diagnosis_criteria(
    db: Session,
    *,
    criteria_id: str,
    diagnosis_key: str,
    diagnosis_name: str,
    aliases: list[str],
    required_evidence: list[str],
    decision: str,
    remark_template: str,
    severity: str,
    priority: int,
    is_active: bool,
    version: str,
    source: str,
) -> int:
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
        {
            "criteria_id": criteria_id,
            "diagnosis_key": diagnosis_key,
            "diagnosis_name": diagnosis_name,
            "aliases_json": json.dumps(aliases),
            "required_evidence_json": json.dumps(required_evidence),
            "decision": decision,
            "remark_template": remark_template,
            "severity": severity,
            "priority": int(priority),
            "is_active": bool(is_active),
            "version": version,
            "source": source,
        },
    ).mappings().one()
    return int(row["id"])


def update_diagnosis_criteria(
    db: Session,
    *,
    row_id: int,
    criteria_id: str,
    diagnosis_key: str,
    diagnosis_name: str,
    aliases: list[str],
    required_evidence: list[str],
    decision: str,
    remark_template: str,
    severity: str,
    priority: int,
    is_active: bool,
    version: str,
    source: str,
) -> dict[str, Any] | None:
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
                source = :source,
                updated_at = NOW()
            WHERE id = :id
            RETURNING id, criteria_id, diagnosis_key, diagnosis_name, aliases_json,
                      required_evidence_json, decision,
                      COALESCE(remark_template,'') AS remark_template,
                      severity, priority, is_active,
                      COALESCE(version,'1.0') AS version,
                      COALESCE(source,'manual') AS source,
                      updated_at
            """
        ),
        {
            "id": int(row_id),
            "criteria_id": criteria_id,
            "diagnosis_key": diagnosis_key,
            "diagnosis_name": diagnosis_name,
            "aliases_json": json.dumps(aliases),
            "required_evidence_json": json.dumps(required_evidence),
            "decision": decision,
            "remark_template": remark_template,
            "severity": severity,
            "priority": int(priority),
            "is_active": bool(is_active),
            "version": version,
            "source": source,
        },
    ).mappings().first()
    return dict(row) if row is not None else None


def set_diagnosis_criteria_active(db: Session, *, row_id: int, is_active: bool) -> bool:
    row = db.execute(
        text("UPDATE openai_diagnosis_criteria SET is_active = :is_active WHERE id = :id RETURNING id"),
        {"id": int(row_id), "is_active": bool(is_active)},
    ).mappings().first()
    return row is not None


def delete_diagnosis_criteria(db: Session, *, row_id: int) -> bool:
    row = db.execute(
        text("DELETE FROM openai_diagnosis_criteria WHERE id = :id RETURNING id"),
        {"id": int(row_id)},
    ).mappings().first()
    return row is not None

