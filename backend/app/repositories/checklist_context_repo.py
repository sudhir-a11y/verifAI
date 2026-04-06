from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_claim_context_row(db: Session, *, claim_id: UUID) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT id, external_claim_id, patient_name, patient_identifier, status, priority, source_channel, tags
            FROM claims
            WHERE id = :claim_id
            """
        ),
        {"claim_id": str(claim_id)},
    ).mappings().first()
    return dict(row) if row is not None else None


def list_latest_extractions_per_document(db: Session, *, claim_id: UUID) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            WITH latest_per_document AS (
                SELECT
                    id,
                    document_id,
                    extracted_entities,
                    evidence_refs,
                    model_name,
                    extraction_version,
                    created_at,
                    ROW_NUMBER() OVER (PARTITION BY document_id ORDER BY created_at DESC) AS rn
                FROM document_extractions
                WHERE claim_id = :claim_id
            )
            SELECT id, document_id, extracted_entities, evidence_refs, model_name, extraction_version, created_at
            FROM latest_per_document
            WHERE rn = 1
            ORDER BY created_at DESC
            """
        ),
        {"claim_id": str(claim_id)},
    ).mappings().all()
    return [dict(r) for r in rows]

