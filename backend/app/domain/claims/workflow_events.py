from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.workflow_events_repo import list_workflow_events


def get_claim_workflow_events(
    db: Session,
    claim_id: UUID,
    *,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Domain use-case: retrieve workflow event timeline for a claim."""
    return list_workflow_events(db, claim_id, limit=limit, offset=offset)
