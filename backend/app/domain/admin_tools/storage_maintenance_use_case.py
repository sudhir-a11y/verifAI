from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.repositories import admin_storage_maintenance_repo


def storage_maintenance_summary(db: Session) -> dict[str, Any]:
    totals = admin_storage_maintenance_repo.get_storage_maintenance_totals(db)
    buckets = admin_storage_maintenance_repo.list_document_bucket_counts(db)

    return {
        "total_documents": int(totals.get("total_documents") or 0),
        "total_bytes": int(totals.get("total_bytes") or 0),
        "parse_status_counts": {
            "pending": int(totals.get("pending_count") or 0),
            "processing": int(totals.get("processing_count") or 0),
            "succeeded": int(totals.get("succeeded_count") or 0),
            "failed": int(totals.get("failed_count") or 0),
        },
        "buckets": [{"bucket": str(r.get("bucket") or "unknown"), "count": int(r.get("count") or 0)} for r in buckets],
    }

