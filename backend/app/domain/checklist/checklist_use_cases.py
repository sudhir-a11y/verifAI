from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.checklist import ChecklistLatestResponse, ChecklistRunRequest, ChecklistRunResponse
from app.domain.checklist.pipeline import (
    ClaimNotFoundError,
    get_latest_claim_checklist as _get_latest_claim_checklist,
    run_claim_checklist_pipeline as _run_claim_checklist_pipeline,
)


def evaluate_claim_checklist(
    db: Session,
    *,
    claim_id: UUID,
    actor_id: str,
    force_source_refresh: bool,
) -> ChecklistRunResponse:
    return _run_claim_checklist_pipeline(
        db=db,
        claim_id=claim_id,
        actor_id=actor_id,
        force_source_refresh=force_source_refresh,
    )


def get_latest_claim_checklist(db: Session, *, claim_id: UUID) -> ChecklistLatestResponse:
    return _get_latest_claim_checklist(db=db, claim_id=claim_id)
