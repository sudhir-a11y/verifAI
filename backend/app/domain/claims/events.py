from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.workflow_events_repo import emit_workflow_event


def try_record_workflow_event(
    db: Session,
    *,
    claim_id: UUID,
    actor_id: str | None,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    try:
        emit_workflow_event(
            db=db,
            claim_id=claim_id,
            event_type=event_type,
            actor_id=actor_id,
            payload=payload,
        )
        db.commit()
    except Exception:
        db.rollback()

