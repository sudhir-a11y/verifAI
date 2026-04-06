import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def emit_workflow_event(
    db: Session,
    claim_id: UUID,
    event_type: str,
    actor_id: str | None,
    payload: dict[str, Any],
    *,
    actor_type: str = "user",
    occurred_at: Any | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO workflow_events (claim_id, actor_type, actor_id, event_type, event_payload, occurred_at)
            VALUES (:claim_id, :actor_type, :actor_id, :event_type, CAST(:event_payload AS jsonb), COALESCE(:occurred_at, NOW()))
            """
        ),
        {
            "claim_id": str(claim_id),
            "actor_type": actor_type,
            "actor_id": actor_id,
            "event_type": event_type,
            "event_payload": json.dumps(payload),
            "occurred_at": occurred_at,
        },
    )


def list_workflow_events(
    db: Session,
    claim_id: UUID,
    *,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """List workflow events for a specific claim, ordered by occurrence time descending."""
    query = text(
        """
        SELECT 
            we.id,
            we.claim_id,
            we.actor_type,
            we.actor_id,
            we.event_type,
            we.event_payload,
            we.occurred_at
        FROM workflow_events we
        WHERE we.claim_id = :claim_id
        ORDER BY we.occurred_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    result = db.execute(query, {"claim_id": str(claim_id), "limit": limit, "offset": offset})
    rows = result.mappings().all()

    items = []
    for row in rows:
        payload = dict(row)
        # Parse JSON payload if it's a string
        if isinstance(payload.get("event_payload"), str):
            try:
                payload["event_payload"] = json.loads(payload["event_payload"])
            except (json.JSONDecodeError, TypeError):
                pass
        items.append(payload)

    # Get total count
    count_query = text(
        """
        SELECT COUNT(*) as total
        FROM workflow_events
        WHERE claim_id = :claim_id
        """
    )
    count_result = db.execute(count_query, {"claim_id": str(claim_id)})
    total = count_result.mappings().first()["total"]

    return {"items": items, "total": total, "limit": limit, "offset": offset}
