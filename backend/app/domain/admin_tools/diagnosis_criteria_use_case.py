from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.admin_tools.normalization import normalize_json_list, normalize_rule_decision, normalize_severity
from app.repositories import admin_diagnosis_criteria_repo


@dataclass(frozen=True)
class DiagnosisCriteriaAlreadyExistsError(Exception):
    message: str = "criteria_id/diagnosis_key already exists"


@dataclass(frozen=True)
class DiagnosisCriteriaNotFoundError(Exception):
    message: str = "diagnosis criteria not found"


def list_diagnosis_criteria(
    db: Session,
    *,
    search: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    total = admin_diagnosis_criteria_repo.count_diagnosis_criteria(db, search=search)
    rows = admin_diagnosis_criteria_repo.list_diagnosis_criteria(db, search=search, limit=limit, offset=offset)

    items: list[dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "id": int(row["id"]),
                "criteria_id": str(row.get("criteria_id") or ""),
                "diagnosis_key": str(row.get("diagnosis_key") or ""),
                "diagnosis_name": str(row.get("diagnosis_name") or ""),
                "aliases": normalize_json_list(row.get("aliases_json")),
                "required_evidence": normalize_json_list(row.get("required_evidence_json")),
                "decision": str(row.get("decision") or "QUERY"),
                "remark_template": str(row.get("remark_template") or ""),
                "severity": str(row.get("severity") or "SOFT_QUERY"),
                "priority": int(row.get("priority") or 999),
                "is_active": bool(row.get("is_active")),
                "version": str(row.get("version") or "1.0"),
                "source": str(row.get("source") or "manual"),
                "updated_at": row.get("updated_at"),
            }
        )
    return {"total": total, "items": items}


def create_diagnosis_criteria(
    db: Session,
    *,
    payload,
    created_by_username: str,
) -> dict[str, Any]:
    diagnosis_key = (payload.diagnosis_key or payload.diagnosis_name).strip().lower().replace(" ", "_")
    try:
        row_id = admin_diagnosis_criteria_repo.insert_diagnosis_criteria(
            db,
            criteria_id=payload.criteria_id.strip().upper(),
            diagnosis_key=diagnosis_key,
            diagnosis_name=payload.diagnosis_name.strip(),
            aliases=normalize_json_list(payload.aliases),
            required_evidence=normalize_json_list(payload.required_evidence),
            decision=normalize_rule_decision(payload.decision),
            remark_template=(payload.remark_template or "").strip(),
            severity=normalize_severity(payload.severity),
            priority=int(payload.priority),
            is_active=bool(payload.is_active),
            version=payload.version.strip() or "1.0",
            source=f"manual:{created_by_username}",
        )
    except IntegrityError as exc:
        raise DiagnosisCriteriaAlreadyExistsError() from exc
    return {"id": int(row_id), "message": "diagnosis criteria created"}


def update_diagnosis_criteria(
    db: Session,
    *,
    row_id: int,
    payload,
    updated_by_username: str,
) -> dict[str, Any]:
    diagnosis_key = (payload.diagnosis_key or payload.diagnosis_name).strip().lower().replace(" ", "_")
    try:
        row = admin_diagnosis_criteria_repo.update_diagnosis_criteria(
            db,
            row_id=row_id,
            criteria_id=payload.criteria_id.strip().upper(),
            diagnosis_key=diagnosis_key,
            diagnosis_name=payload.diagnosis_name.strip(),
            aliases=normalize_json_list(payload.aliases),
            required_evidence=normalize_json_list(payload.required_evidence),
            decision=normalize_rule_decision(payload.decision),
            remark_template=(payload.remark_template or "").strip(),
            severity=normalize_severity(payload.severity),
            priority=int(payload.priority),
            is_active=bool(payload.is_active),
            version=payload.version.strip() or "1.0",
            source=f"manual:{updated_by_username}",
        )
    except IntegrityError as exc:
        raise DiagnosisCriteriaAlreadyExistsError() from exc

    if row is None:
        raise DiagnosisCriteriaNotFoundError()
    return {"id": int(row["id"]), "message": "diagnosis criteria updated"}


def toggle_diagnosis_criteria(db: Session, *, row_id: int, is_active: bool) -> dict[str, Any]:
    ok = admin_diagnosis_criteria_repo.set_diagnosis_criteria_active(db, row_id=row_id, is_active=is_active)
    if not ok:
        raise DiagnosisCriteriaNotFoundError()
    return {"id": int(row_id), "is_active": bool(is_active)}


def delete_diagnosis_criteria(db: Session, *, row_id: int) -> dict[str, Any]:
    deleted = admin_diagnosis_criteria_repo.delete_diagnosis_criteria(db, row_id=row_id)
    if not deleted:
        raise DiagnosisCriteriaNotFoundError()
    return {"deleted": True}

