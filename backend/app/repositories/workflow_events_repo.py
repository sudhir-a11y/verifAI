import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


def ensure_table(db: Session) -> None:
    """Ensure the workflow_events table exists and has required columns."""
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS workflow_events (
                id BIGSERIAL PRIMARY KEY,
                claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
                actor_type TEXT NOT NULL DEFAULT 'user',
                actor_id TEXT NULL,
                event_type TEXT NOT NULL,
                event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )

    # Harden older schemas without breaking if already up-to-date.
    db.execute(text("ALTER TABLE workflow_events ADD COLUMN IF NOT EXISTS actor_type TEXT"))
    db.execute(text("ALTER TABLE workflow_events ADD COLUMN IF NOT EXISTS actor_id TEXT"))
    db.execute(text("ALTER TABLE workflow_events ADD COLUMN IF NOT EXISTS event_type TEXT"))
    db.execute(text("ALTER TABLE workflow_events ADD COLUMN IF NOT EXISTS event_payload JSONB"))
    db.execute(text("ALTER TABLE workflow_events ADD COLUMN IF NOT EXISTS occurred_at TIMESTAMPTZ"))

    db.execute(text("CREATE INDEX IF NOT EXISTS idx_workflow_events_claim_id ON workflow_events(claim_id)"))
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_workflow_events_claim_id_occurred_at ON workflow_events(claim_id, occurred_at DESC)"
        )
    )


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
    try:
        ensure_table(db)
    except SQLAlchemyError:
        # Let the insert attempt surface the actual failure.
        pass
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
    try:
        ensure_table(db)
    except SQLAlchemyError:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}
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
    try:
        result = db.execute(query, {"claim_id": str(claim_id), "limit": limit, "offset": offset})
        rows = result.mappings().all()
    except SQLAlchemyError:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    items: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        if isinstance(payload.get("event_payload"), str):
            try:
                payload["event_payload"] = json.loads(payload["event_payload"])
            except (json.JSONDecodeError, TypeError):
                pass
        items.append(payload)

    count_query = text(
        """
        SELECT COUNT(*) as total
        FROM workflow_events
        WHERE claim_id = :claim_id
        """
    )
    try:
        count_result = db.execute(count_query, {"claim_id": str(claim_id)})
        count_row = count_result.mappings().first()
        if not count_row:
            total = 0
        else:
            try:
                total = int(count_row["total"] or 0)
            except Exception:
                total = 0
    except SQLAlchemyError:
        total = 0

    return {"items": items, "total": total, "limit": limit, "offset": offset}
