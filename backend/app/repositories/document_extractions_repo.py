"""Repository for document_extractions table."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def delete_by_claim_id(db: Session, *, claim_id: str) -> int:
    return int(
        db.execute(text("DELETE FROM document_extractions WHERE claim_id = :claim_id"), {"claim_id": claim_id}).rowcount
        or 0
    )


def list_by_document_id(
    db: Session, *, document_id: str, limit: int = 50, offset: int = 0
) -> tuple[list[dict[str, Any]], int]:
    """List extractions for a document. Returns (rows, total)."""
    total_row = db.execute(
        text("SELECT COUNT(*) FROM document_extractions WHERE document_id = :document_id"),
        {"document_id": document_id},
    ).first()
    total = int(total_row[0]) if total_row else 0

    rows = db.execute(
        text(
            """
            SELECT * FROM document_extractions
            WHERE document_id = :document_id
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"document_id": document_id, "limit": limit, "offset": offset},
    ).mappings().all()
    return [dict(r) for r in rows], total


def insert_extraction(db: Session, params: dict[str, Any]) -> int:
    """Insert a new extraction. Returns the new id."""
    row = db.execute(
        text(
            """
            INSERT INTO document_extractions (
                claim_id, document_id, extracted_entities,
                evidence_refs, raw_response_json, provider,
                confidence, created_at
            ) VALUES (
                :claim_id, :document_id,
                CAST(:extracted_entities AS jsonb),
                CAST(:evidence_refs AS jsonb),
                :raw_response_json, :provider,
                :confidence, NOW()
            )
            RETURNING id
            """
        ),
        params,
    ).first()
    return int(row[0])


def count_by_document_id(db: Session, document_id: str) -> int:
    """Count extractions for a document."""
    row = db.execute(
        text("SELECT COUNT(*) FROM document_extractions WHERE document_id = :document_id"),
        {"document_id": document_id},
    ).first()
    return int(row[0]) if row else 0


def delete_by_claim_and_document(db: Session, claim_id: str, document_id: str) -> int:
    """Delete extractions for a specific claim+document."""
    result = db.execute(
        text(
            "DELETE FROM document_extractions WHERE claim_id = :claim_id AND document_id = :document_id"
        ),
        {"claim_id": claim_id, "document_id": document_id},
    )
    return int(result.rowcount or 0)


def get_latest_per_claim(db: Session, claim_id: str) -> dict[str, Any] | None:
    """Get the latest extraction for a claim."""
    row = db.execute(
        text(
            """
            SELECT * FROM document_extractions
            WHERE claim_id = :claim_id
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"claim_id": claim_id},
    ).mappings().first()
    return dict(row) if row else None
