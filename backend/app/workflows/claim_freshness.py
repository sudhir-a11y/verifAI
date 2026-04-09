from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


_SKEW_SECONDS = 5


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def latest_claim_inputs_at(db: Session, *, claim_id: UUID) -> datetime | None:
    row = db.execute(
        text(
            """
            SELECT GREATEST(
                COALESCE((SELECT MAX(uploaded_at) FROM claim_documents WHERE claim_id = :claim_id), TIMESTAMPTZ 'epoch'),
                COALESCE((SELECT MAX(created_at) FROM document_extractions WHERE claim_id = :claim_id), TIMESTAMPTZ 'epoch')
            ) AS latest_inputs_at
            """
        ),
        {"claim_id": str(claim_id)},
    ).mappings().first()
    value = _as_utc((row or {}).get("latest_inputs_at"))
    if value is None:
        return None
    if value <= datetime(1971, 1, 1, tzinfo=timezone.utc):
        return None
    return value


def is_artifact_fresh_for_claim(
    db: Session,
    *,
    claim_id: UUID,
    artifact_generated_at: datetime | None,
) -> bool:
    generated = _as_utc(artifact_generated_at)
    if generated is None:
        return False
    latest_inputs = latest_claim_inputs_at(db, claim_id=claim_id)
    if latest_inputs is None:
        return True
    return generated >= (latest_inputs - timedelta(seconds=_SKEW_SECONDS))

