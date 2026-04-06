"""Repository for claim_documents table."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def reset_parse_status(db: Session, *, claim_id: str) -> int:
    return int(
        db.execute(
            text(
                """
                UPDATE claim_documents
                SET parse_status = 'pending',
                    parsed_at = NULL
                WHERE claim_id = :claim_id
                """
            ),
            {"claim_id": claim_id},
        ).rowcount
        or 0
    )


def get_by_id(db: Session, document_id: str) -> dict[str, Any] | None:
    """Get a single document by id."""
    row = db.execute(
        text("SELECT * FROM claim_documents WHERE id = :id LIMIT 1"),
        {"id": document_id},
    ).mappings().first()
    return dict(row) if row else None


def list_by_claim_id(db: Session, claim_id: str) -> list[dict[str, Any]]:
    """List all documents for a claim."""
    rows = db.execute(
        text(
            "SELECT * FROM claim_documents WHERE claim_id = :claim_id ORDER BY created_at ASC"
        ),
        {"claim_id": claim_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def insert_document(db: Session, params: dict[str, Any]) -> int:
    """Insert a new document. Returns the new id."""
    row = db.execute(
        text(
            """
            INSERT INTO claim_documents (
                claim_id, file_name, file_type, file_size_bytes,
                storage_key, metadata, parse_status, created_at
            ) VALUES (
                :claim_id, :file_name, :file_type, :file_size_bytes,
                :storage_key, CAST(:metadata AS jsonb), :parse_status, NOW()
            )
            RETURNING id
            """
        ),
        params,
    ).first()
    return int(row[0])


def delete_by_id(db: Session, document_id: str) -> bool:
    """Delete a document by id. Returns True if deleted."""
    result = db.execute(
        text("DELETE FROM claim_documents WHERE id = :id"),
        {"id": document_id},
    )
    return bool(result.rowcount)


def count_by_claim_id(db: Session, claim_id: str) -> int:
    """Count documents for a claim."""
    row = db.execute(
        text("SELECT COUNT(*) FROM claim_documents WHERE claim_id = :claim_id"),
        {"claim_id": claim_id},
    ).first()
    return int(row[0]) if row else 0


def exists(db: Session, document_id: str, claim_id: str) -> bool:
    """Check if a document exists for a specific claim."""
    row = db.execute(
        text(
            "SELECT 1 FROM claim_documents WHERE id = :id AND claim_id = :claim_id LIMIT 1"
        ),
        {"id": document_id, "claim_id": claim_id},
    ).first()
    return row is not None


def update_parse_status(db: Session, document_id: str, parse_status: str) -> None:
    """Update the parse status of a document."""
    db.execute(
        text(
            """
            UPDATE claim_documents
            SET parse_status = :parse_status,
                parsed_at = CASE WHEN :parse_status = 'succeeded' THEN NOW() ELSE parsed_at END
            WHERE id = :id
            """
        ),
        {"id": document_id, "parse_status": parse_status},
    )


def get_storage_maintenance_summary(db: Session) -> dict[str, Any]:
    """Get storage summary across all documents."""
    row = db.execute(
        text(
            """
            SELECT
                COUNT(*) AS total_documents,
                COALESCE(SUM(file_size_bytes), 0) AS total_bytes,
                COUNT(*) FILTER (WHERE parse_status = 'pending') AS pending_count,
                COUNT(*) FILTER (WHERE parse_status = 'processing') AS processing_count,
                COUNT(*) FILTER (WHERE parse_status = 'succeeded') AS succeeded_count,
                COUNT(*) FILTER (WHERE parse_status = 'failed') AS failed_count
            FROM claim_documents
            """
        ),
    ).mappings().first()
    return dict(row) if row else {}


def get_bucket_stats(db: Session) -> list[dict[str, Any]]:
    """Get document counts grouped by storage bucket."""
    rows = db.execute(
        text(
            """
            SELECT COALESCE(metadata->>'bucket', 'unknown') AS bucket, COUNT(*) AS count
            FROM claim_documents
            GROUP BY COALESCE(metadata->>'bucket', 'unknown')
            ORDER BY count DESC
            """
        ),
    ).mappings().all()
    return [dict(r) for r in rows]


def get_assigned_doctor_id_for_document(db: Session, document_id: str) -> str | None:
    """Get the assigned doctor ID for a document via its claim."""
    row = db.execute(
        text(
            """
            SELECT c.assigned_doctor_id
            FROM claim_documents d
            JOIN claims c ON c.id = d.claim_id
            WHERE d.id = :document_id
            """
        ),
        {"document_id": document_id},
    ).mappings().first()
    if row is None:
        return None
    return str(row.get("assigned_doctor_id") or "")
