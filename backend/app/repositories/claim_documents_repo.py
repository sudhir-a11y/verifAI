"""Repository for claim_documents table."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import bindparam, text
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


# ----------------------------
# Newer schema helpers (mime_type/uploaded_at/etc.)
# Keep these separate from the legacy helpers above so existing callers remain stable.
# ----------------------------


def list_storage_key_and_metadata_for_claim(db: Session, *, claim_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        text("SELECT storage_key, metadata FROM claim_documents WHERE claim_id = :claim_id"),
        {"claim_id": claim_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def insert_legacy_external_document_if_missing(
    db: Session,
    *,
    claim_id: str,
    storage_key: str,
    file_name: str,
    mime_type: str,
    metadata: dict[str, Any],
) -> str | None:
    row = db.execute(
        text(
            """
            INSERT INTO claim_documents (
                claim_id,
                storage_key,
                file_name,
                mime_type,
                file_size_bytes,
                checksum_sha256,
                parse_status,
                retention_class,
                uploaded_by,
                metadata
            )
            VALUES (
                :claim_id,
                :storage_key,
                :file_name,
                :mime_type,
                NULL,
                NULL,
                'succeeded',
                'standard',
                'legacy_sync',
                CAST(:metadata AS jsonb)
            )
            ON CONFLICT (claim_id, storage_key) DO NOTHING
            RETURNING id
            """
        ),
        {
            "claim_id": claim_id,
            "storage_key": storage_key,
            "file_name": file_name,
            "mime_type": mime_type,
            "metadata": json.dumps(metadata),
        },
    ).mappings().first()
    if row is None:
        return None
    return str(row.get("id") or "") or None


def insert_s3_prefix_document_if_missing(
    db: Session,
    *,
    claim_id: str,
    storage_key: str,
    file_name: str,
    mime_type: str,
    file_size_bytes: int,
    metadata: dict[str, Any],
) -> str | None:
    row = db.execute(
        text(
            """
            INSERT INTO claim_documents (
                claim_id,
                storage_key,
                file_name,
                mime_type,
                file_size_bytes,
                checksum_sha256,
                parse_status,
                retention_class,
                uploaded_by,
                uploaded_at,
                metadata
            )
            VALUES (
                :claim_id,
                :storage_key,
                :file_name,
                :mime_type,
                :file_size_bytes,
                NULL,
                'succeeded',
                'standard',
                'legacy_sync',
                NOW(),
                CAST(:metadata AS jsonb)
            )
            ON CONFLICT (claim_id, storage_key) DO NOTHING
            RETURNING id
            """
        ),
        {
            "claim_id": claim_id,
            "storage_key": storage_key,
            "file_name": file_name,
            "mime_type": mime_type,
            "file_size_bytes": int(file_size_bytes or 0),
            "metadata": json.dumps(metadata),
        },
    ).mappings().first()
    if row is None:
        return None
    return str(row.get("id") or "") or None


def insert_uploaded_document_returning_row(
    db: Session,
    *,
    claim_id: str,
    storage_key: str,
    file_name: str,
    mime_type: str,
    file_size_bytes: int,
    checksum_sha256: str,
    retention_class: str,
    uploaded_by: str | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            INSERT INTO claim_documents (
                claim_id,
                storage_key,
                file_name,
                mime_type,
                file_size_bytes,
                checksum_sha256,
                parse_status,
                retention_class,
                uploaded_by,
                metadata
            )
            VALUES (
                :claim_id,
                :storage_key,
                :file_name,
                :mime_type,
                :file_size_bytes,
                :checksum_sha256,
                'pending',
                :retention_class,
                :uploaded_by,
                CAST(:metadata AS jsonb)
            )
            RETURNING
                id,
                claim_id,
                storage_key,
                file_name,
                mime_type,
                file_size_bytes,
                checksum_sha256,
                parse_status,
                page_count,
                retention_class,
                uploaded_by,
                uploaded_at,
                parsed_at,
                metadata
            """
        ),
        {
            "claim_id": claim_id,
            "storage_key": storage_key,
            "file_name": file_name,
            "mime_type": mime_type,
            "file_size_bytes": int(file_size_bytes or 0),
            "checksum_sha256": checksum_sha256,
            "retention_class": retention_class,
            "uploaded_by": uploaded_by,
            "metadata": json.dumps(metadata),
        },
    ).mappings().one()
    return dict(row)


def update_document_metadata_merge(db: Session, *, document_id: str, merge_meta: dict[str, Any]) -> None:
    db.execute(
        text(
            """
            UPDATE claim_documents
            SET metadata = COALESCE(metadata, '{}'::jsonb) || CAST(:merge_meta AS jsonb)
            WHERE id = :document_id
            """
        ),
        {"document_id": document_id, "merge_meta": json.dumps(merge_meta)},
    )


def get_document_row_by_id(db: Session, *, document_id: str) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT
                id,
                claim_id,
                storage_key,
                file_name,
                mime_type,
                file_size_bytes,
                checksum_sha256,
                parse_status,
                page_count,
                retention_class,
                uploaded_by,
                uploaded_at,
                parsed_at,
                metadata
            FROM claim_documents
            WHERE id = :document_id
            """
        ),
        {"document_id": document_id},
    ).mappings().first()
    return dict(row) if row is not None else None


def list_documents_paginated_for_claim(
    db: Session,
    *,
    claim_id: str,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT
                id,
                claim_id,
                storage_key,
                file_name,
                mime_type,
                file_size_bytes,
                checksum_sha256,
                parse_status,
                page_count,
                retention_class,
                uploaded_by,
                uploaded_at,
                parsed_at,
                metadata
            FROM claim_documents
            WHERE claim_id = :claim_id
            ORDER BY uploaded_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"claim_id": claim_id, "limit": int(limit or 0), "offset": int(offset or 0)},
    ).mappings().all()
    return [dict(r) for r in rows]


def update_parse_status_returning_row(
    db: Session,
    *,
    document_id: str,
    parse_status: str,
) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            UPDATE claim_documents
            SET parse_status = :parse_status,
                parsed_at = CASE WHEN :parse_status = 'succeeded' THEN NOW() ELSE parsed_at END
            WHERE id = :document_id
            RETURNING
                id,
                claim_id,
                storage_key,
                file_name,
                mime_type,
                file_size_bytes,
                checksum_sha256,
                parse_status,
                page_count,
                retention_class,
                uploaded_by,
                uploaded_at,
                parsed_at,
                metadata
            """
        ),
        {"document_id": document_id, "parse_status": parse_status},
    ).mappings().first()
    return dict(row) if row is not None else None


def get_storage_key_and_metadata_by_id(db: Session, *, document_id: str) -> dict[str, Any] | None:
    row = db.execute(
        text("SELECT id, storage_key, metadata FROM claim_documents WHERE id = :document_id"),
        {"document_id": document_id},
    ).mappings().first()
    return dict(row) if row is not None else None


def list_docs_for_bulk_delete(
    db: Session,
    *,
    claim_id: str,
    document_ids: list[str],
) -> list[dict[str, Any]]:
    if not document_ids:
        return []
    query = text(
        """
        SELECT id, storage_key, metadata
        FROM claim_documents
        WHERE claim_id = :claim_id
          AND id IN :document_ids
        """
    ).bindparams(bindparam("document_ids", expanding=True))
    rows = db.execute(query, {"claim_id": claim_id, "document_ids": document_ids}).mappings().all()
    return [dict(r) for r in rows]


def delete_docs_for_claim_returning_ids(
    db: Session,
    *,
    claim_id: str,
    document_ids: list[str],
) -> list[str]:
    if not document_ids:
        return []
    query = text(
        """
        DELETE FROM claim_documents
        WHERE claim_id = :claim_id
          AND id IN :document_ids
        RETURNING id
        """
    ).bindparams(bindparam("document_ids", expanding=True))
    rows = db.execute(query, {"claim_id": claim_id, "document_ids": document_ids}).mappings().all()
    return [str(r.get("id") or "") for r in rows if str(r.get("id") or "")]
