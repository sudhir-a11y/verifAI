from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_storage_maintenance_totals(db: Session) -> dict:
    totals = db.execute(
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
        )
    ).mappings().one()
    return dict(totals)


def list_document_bucket_counts(db: Session) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT COALESCE(metadata->>'bucket', 'unknown') AS bucket, COUNT(*) AS count
            FROM claim_documents
            GROUP BY COALESCE(metadata->>'bucket', 'unknown')
            ORDER BY count DESC
            """
        )
    ).mappings().all()
    return [dict(row) for row in rows]

