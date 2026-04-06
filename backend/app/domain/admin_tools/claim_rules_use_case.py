from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.admin_tools.normalization import normalize_json_list, normalize_rule_decision, normalize_severity
from app.repositories import admin_claim_rules_repo


@dataclass(frozen=True)
class ClaimRuleAlreadyExistsError(Exception):
    message: str = "rule_id already exists"


@dataclass(frozen=True)
class ClaimRuleNotFoundError(Exception):
    message: str = "rule not found"


def list_claim_rules(
    db: Session,
    *,
    search: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    total = admin_claim_rules_repo.count_claim_rules(db, search=search)
    rows = admin_claim_rules_repo.list_claim_rules(db, search=search, limit=limit, offset=offset)

    items: list[dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "id": int(row["id"]),
                "rule_id": str(row["rule_id"]),
                "name": str(row["name"]),
                "scope": normalize_json_list(row.get("scope_json")),
                "conditions": str(row.get("conditions") or ""),
                "decision": str(row.get("decision") or "QUERY"),
                "remark_template": str(row.get("remark_template") or ""),
                "required_evidence": normalize_json_list(row.get("required_evidence_json")),
                "severity": str(row.get("severity") or "SOFT_QUERY"),
                "priority": int(row.get("priority") or 999),
                "is_active": bool(row.get("is_active")),
                "version": str(row.get("version") or "1.0"),
                "source": str(row.get("source") or "manual"),
                "updated_at": row.get("updated_at"),
            }
        )

    return {"total": total, "items": items}


def create_claim_rule(
    db: Session,
    *,
    payload,
    created_by_username: str,
) -> dict[str, Any]:
    try:
        row_id = admin_claim_rules_repo.insert_claim_rule(
            db,
            rule_id=payload.rule_id.strip().upper(),
            name=payload.name.strip(),
            scope=normalize_json_list(payload.scope),
            conditions=(payload.conditions or "").strip(),
            decision=normalize_rule_decision(payload.decision),
            remark_template=(payload.remark_template or "").strip(),
            required_evidence=normalize_json_list(payload.required_evidence),
            severity=normalize_severity(payload.severity),
            priority=int(payload.priority),
            is_active=bool(payload.is_active),
            version=payload.version.strip() or "1.0",
            source=f"manual:{created_by_username}",
        )
    except IntegrityError as exc:
        raise ClaimRuleAlreadyExistsError() from exc

    return {"id": int(row_id), "message": "rule created"}


def update_claim_rule(
    db: Session,
    *,
    row_id: int,
    payload,
    updated_by_username: str,
) -> dict[str, Any]:
    try:
        row = admin_claim_rules_repo.update_claim_rule(
            db,
            row_id=row_id,
            rule_id=payload.rule_id.strip().upper(),
            name=payload.name.strip(),
            scope=normalize_json_list(payload.scope),
            conditions=(payload.conditions or "").strip(),
            decision=normalize_rule_decision(payload.decision),
            remark_template=(payload.remark_template or "").strip(),
            required_evidence=normalize_json_list(payload.required_evidence),
            severity=normalize_severity(payload.severity),
            priority=int(payload.priority),
            is_active=bool(payload.is_active),
            version=payload.version.strip() or "1.0",
            source=f"manual:{updated_by_username}",
        )
    except IntegrityError as exc:
        raise ClaimRuleAlreadyExistsError("rule_id conflict") from exc

    if row is None:
        raise ClaimRuleNotFoundError()

    return {"id": int(row["id"]), "message": "rule updated"}


def toggle_claim_rule(db: Session, *, row_id: int, is_active: bool) -> dict[str, Any]:
    ok = admin_claim_rules_repo.set_claim_rule_active(db, row_id=row_id, is_active=is_active)
    if not ok:
        raise ClaimRuleNotFoundError()
    return {"id": int(row_id), "is_active": bool(is_active)}


def delete_claim_rule(db: Session, *, row_id: int) -> dict[str, Any]:
    deleted = admin_claim_rules_repo.delete_claim_rule(db, row_id=row_id)
    if not deleted:
        raise ClaimRuleNotFoundError()
    return {"deleted": True}

