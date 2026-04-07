import json
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories import claims_repo, workflow_events_repo
from app.schemas.claim import (
    ClaimAssignmentRequest,
    ClaimListResponse,
    ClaimResponse,
    ClaimStatus,
    ClaimStatusUpdateRequest,
    CreateClaimRequest,
)


class DuplicateClaimIdError(Exception):
    pass


class ClaimNotFoundError(Exception):
    pass


def _normalize_tags(raw_tags: Any) -> list[str]:
    if raw_tags is None:
        return []
    if isinstance(raw_tags, list):
        return [str(tag) for tag in raw_tags]
    if isinstance(raw_tags, str):
        try:
            parsed = json.loads(raw_tags)
            if isinstance(parsed, list):
                return [str(tag) for tag in parsed]
        except json.JSONDecodeError:
            return []
    return []

def _normalize_status(raw_status: Any) -> str:
    value = str(raw_status or "").strip().lower()
    if not value:
        return ClaimStatus.waiting_for_documents.value

    # Common legacy/variant values.
    aliases = {
        "ready": ClaimStatus.ready_for_assignment.value,
        "ready_for_assign": ClaimStatus.ready_for_assignment.value,
        "waiting": ClaimStatus.waiting_for_documents.value,
        "waiting_documents": ClaimStatus.waiting_for_documents.value,
        "inreview": ClaimStatus.in_review.value,
        "review": ClaimStatus.in_review.value,
        "needsreview": ClaimStatus.in_review.value,
        "qc": ClaimStatus.needs_qc.value,
        "need_qc": ClaimStatus.needs_qc.value,
        "needsqc": ClaimStatus.needs_qc.value,
        "done": ClaimStatus.completed.value,
        "close": ClaimStatus.completed.value,
        "closed": ClaimStatus.completed.value,
        "cancelled": ClaimStatus.withdrawn.value,
        "canceled": ClaimStatus.withdrawn.value,
    }
    if value in aliases:
        return aliases[value]

    # Exact match against known statuses.
    allowed = {item.value for item in ClaimStatus}
    if value in allowed:
        return value

    # Defensive default to avoid 500s on bad data.
    return ClaimStatus.waiting_for_documents.value


def _to_claim_response(row: dict[str, Any]) -> ClaimResponse:
    row["tags"] = _normalize_tags(row.get("tags"))
    row["status"] = _normalize_status(row.get("status"))
    return ClaimResponse.model_validate(row)


def create_claim(db: Session, payload: CreateClaimRequest, actor_id: str | None = None) -> ClaimResponse:
    try:
        row = claims_repo.insert_claim(db, payload)
    except claims_repo.DuplicateClaimIdDbError as exc:
        raise DuplicateClaimIdError from exc

    claim = _to_claim_response(row)
    workflow_events_repo.emit_workflow_event(
        db=db,
        claim_id=claim.id,
        event_type="claim_created",
        actor_id=actor_id,
        payload={"status": claim.status.value},
    )
    db.commit()
    return claim


def list_claims(
    db: Session,
    status: ClaimStatus | None,
    assigned_doctor_id: str | None,
    limit: int,
    offset: int,
) -> ClaimListResponse:
    total, rows = claims_repo.list_claim_rows(db, status, assigned_doctor_id, limit, offset)
    items = [_to_claim_response(r) for r in rows]
    return ClaimListResponse(total=total, items=items)


def get_claim(db: Session, claim_id: UUID) -> ClaimResponse:
    row = claims_repo.get_claim_by_id(db, claim_id)
    if row is None:
        raise ClaimNotFoundError
    return _to_claim_response(row)


def update_claim_status(db: Session, claim_id: UUID, payload: ClaimStatusUpdateRequest) -> ClaimResponse:
    row = claims_repo.update_claim_status_row(db, claim_id, payload.status)
    if row is None:
        db.rollback()
        raise ClaimNotFoundError

    claim = _to_claim_response(row)
    workflow_events_repo.emit_workflow_event(
        db=db,
        claim_id=claim.id,
        event_type="claim_status_updated",
        actor_id=payload.actor_id,
        payload={"status": claim.status.value, "note": payload.note},
    )
    db.commit()
    return claim


def assign_claim(db: Session, claim_id: UUID, payload: ClaimAssignmentRequest) -> ClaimResponse:
    row = claims_repo.assign_claim_row(
        db,
        claim_id,
        payload.assigned_doctor_id,
        status=payload.status,
    )
    if row is None:
        db.rollback()
        raise ClaimNotFoundError

    claim = _to_claim_response(row)
    workflow_events_repo.emit_workflow_event(
        db=db,
        claim_id=claim.id,
        event_type="claim_assigned",
        actor_id=payload.actor_id,
        payload={
            "assigned_doctor_id": payload.assigned_doctor_id,
            "status": claim.status.value,
        },
    )
    db.commit()
    return claim
