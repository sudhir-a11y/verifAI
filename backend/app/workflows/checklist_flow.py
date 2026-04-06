from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.checklist.checklist_use_cases import evaluate_claim_checklist
from app.schemas.checklist import ChecklistRunResponse


def run_checklist_for_claim(
    db: Session,
    *,
    claim_id: UUID,
    actor_id: str,
    force_source_refresh: bool = False,
) -> ChecklistRunResponse:
    return evaluate_claim_checklist(
        db,
        claim_id=claim_id,
        actor_id=actor_id,
        force_source_refresh=bool(force_source_refresh),
    )

