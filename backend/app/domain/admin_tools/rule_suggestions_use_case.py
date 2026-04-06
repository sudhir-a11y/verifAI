from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.domain.admin_tools.normalization import normalize_json_list, normalize_rule_decision
from app.repositories import admin_claim_rules_repo, admin_rule_suggestions_repo


@dataclass(frozen=True)
class RuleSuggestionNotFoundError(Exception):
    message: str = "suggestion not found"


@dataclass(frozen=True)
class TargetRuleNotFoundError(Exception):
    message: str = "target rule not found for update suggestion"


def list_rule_suggestions(
    db: Session,
    *,
    status_filter: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    allowed = {"pending", "approved", "rejected", "all"}
    normalized_filter = status_filter if status_filter in allowed else "pending"

    total = admin_rule_suggestions_repo.count_rule_suggestions(db, status_filter=normalized_filter)
    rows = admin_rule_suggestions_repo.list_rule_suggestions(
        db,
        status_filter=normalized_filter,
        limit=limit,
        offset=offset,
    )

    items: list[dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "id": int(row["id"]),
                "source_analysis_id": int(row.get("source_analysis_id") or 0),
                "claim_id": str(row.get("claim_id") or ""),
                "suggestion_type": str(row.get("suggestion_type") or "new_rule"),
                "target_rule_id": str(row.get("target_rule_id") or ""),
                "proposed_rule_id": str(row.get("proposed_rule_id") or ""),
                "suggested_name": str(row.get("suggested_name") or ""),
                "suggested_decision": str(row.get("suggested_decision") or "QUERY"),
                "suggested_conditions": str(row.get("suggested_conditions") or ""),
                "suggested_remark_template": str(row.get("suggested_remark_template") or ""),
                "suggested_required_evidence": normalize_json_list(row.get("suggested_required_evidence_json")),
                "source_context_text": str(row.get("source_context_text") or ""),
                "generator_confidence": int(row.get("generator_confidence") or 0),
                "generator_reasoning": str(row.get("generator_reasoning") or ""),
                "status": str(row.get("status") or "pending"),
                "approved_rule_id": str(row.get("approved_rule_id") or ""),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
        )

    return {"total": total, "items": items}


def _severity_for_decision(decision: str) -> str:
    return "HARD_REJECT" if decision == "REJECT" else "SOFT_QUERY"


def _upsert_claim_rule_from_suggestion(db: Session, suggestion: dict[str, Any], approved_rule_id: str | None) -> str:
    suggestion_type = str(suggestion.get("suggestion_type") or "new_rule").strip().lower()
    target_rule_id = str(suggestion.get("target_rule_id") or "").strip().upper()
    proposed_rule_id = str(suggestion.get("proposed_rule_id") or "").strip().upper()

    final_rule_id = (approved_rule_id or "").strip().upper()
    decision = normalize_rule_decision(str(suggestion.get("suggested_decision") or "QUERY"))

    if suggestion_type in {"update_rule", "implied_rule"}:
        final_rule_id = target_rule_id
        if not admin_claim_rules_repo.claim_rule_exists_by_rule_id(db, rule_id=final_rule_id):
            raise TargetRuleNotFoundError()

        admin_claim_rules_repo.update_claim_rule_by_rule_id_for_suggestion(
            db,
            rule_id=final_rule_id,
            name=str(suggestion.get("suggested_name") or "Suggested rule"),
            conditions=str(suggestion.get("suggested_conditions") or ""),
            decision=decision,
            remark_template=str(suggestion.get("suggested_remark_template") or ""),
            required_evidence=normalize_json_list(suggestion.get("suggested_required_evidence_json")),
            severity=_severity_for_decision(decision),
            source="suggested_update",
        )
        return final_rule_id

    if not final_rule_id:
        if proposed_rule_id:
            final_rule_id = (
                admin_claim_rules_repo.next_claim_rule_id(db)
                if admin_claim_rules_repo.claim_rule_id_exists(db, rule_id=proposed_rule_id)
                else proposed_rule_id
            )
        else:
            final_rule_id = admin_claim_rules_repo.next_claim_rule_id(db)

    admin_claim_rules_repo.upsert_claim_rule_for_suggestion(
        db,
        rule_id=final_rule_id,
        name=str(suggestion.get("suggested_name") or "Suggested rule"),
        conditions=str(suggestion.get("suggested_conditions") or ""),
        decision=decision,
        remark_template=str(suggestion.get("suggested_remark_template") or ""),
        required_evidence=normalize_json_list(suggestion.get("suggested_required_evidence_json")),
        severity=_severity_for_decision(decision),
        source="suggested",
    )
    return final_rule_id


def review_rule_suggestion(
    db: Session,
    *,
    suggestion_id: int,
    payload,
    reviewed_by_username: str,
) -> dict[str, Any]:
    suggestion = admin_rule_suggestions_repo.get_rule_suggestion(db, suggestion_id=suggestion_id)
    if suggestion is None:
        raise RuleSuggestionNotFoundError()

    approved_rule_id = str(payload.approved_rule_id or "").strip().upper() or None
    if payload.status == "approved":
        approved_rule_id = _upsert_claim_rule_from_suggestion(db, suggestion, approved_rule_id)

    row = admin_rule_suggestions_repo.update_rule_suggestion_status(
        db,
        suggestion_id=suggestion_id,
        status=payload.status,
        approved_rule_id=str(approved_rule_id or ""),
        reviewed_by_username=reviewed_by_username,
    )
    if row is None:
        raise RuleSuggestionNotFoundError()

    return {
        "id": int(row["id"]),
        "status": str(row["status"]),
        "approved_rule_id": str(row.get("approved_rule_id") or ""),
    }

