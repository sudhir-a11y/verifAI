from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def count_claim_document_status(db: Session, *, where_sql: str, params: dict[str, Any]) -> int:
    total = db.execute(
        text(
            f"""
            WITH latest_assignment AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    occurred_at AS assigned_at,
                    DATE(occurred_at) AS allotment_date
                FROM workflow_events
                WHERE event_type = 'claim_assigned'
                ORDER BY claim_id, occurred_at DESC
            ),
            doc_stats AS (
                SELECT
                    cd.claim_id,
                    COUNT(*) AS documents,
                    SUM(
                        CASE
                            WHEN (cd.metadata->>'merge_source_file_count') ~ '^[0-9]+$'
                                AND CAST(cd.metadata->>'merge_source_file_count' AS INTEGER) > 0
                                THEN CAST(cd.metadata->>'merge_source_file_count' AS INTEGER)
                            WHEN (cd.metadata->>'merge_accepted_file_count') ~ '^[0-9]+$'
                                AND CAST(cd.metadata->>'merge_accepted_file_count' AS INTEGER) > 0
                                THEN CAST(cd.metadata->>'merge_accepted_file_count' AS INTEGER)
                            ELSE 1
                        END
                    ) AS source_files,
                    MAX(cd.uploaded_at) AS last_upload,
                    (
                        ARRAY_REMOVE(
                            ARRAY_AGG(NULLIF(TRIM(COALESCE(cd.uploaded_by, '')), '') ORDER BY cd.uploaded_at DESC NULLS LAST),
                            NULL
                        )
                    )[1] AS last_uploaded_by
                FROM claim_documents cd
                GROUP BY cd.claim_id
            ),
            latest_report AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    export_uri
                FROM report_versions
                ORDER BY claim_id, version_no DESC
            ),
            upload_meta AS (
                SELECT
                    claim_id,
                    report_export_status,
                    tagging,
                    subtagging,
                    opinion
                FROM claim_report_uploads
            )
            SELECT COUNT(*)
            FROM claims c
            LEFT JOIN latest_assignment la ON la.claim_id = c.id
            LEFT JOIN doc_stats ds ON ds.claim_id = c.id
            LEFT JOIN latest_report rv ON rv.claim_id = c.id
            LEFT JOIN upload_meta um ON um.claim_id = c.id
            {where_sql}
            """
        ),
        params,
    ).scalar_one()
    return int(total or 0)


def list_claim_document_status_rows(
    db: Session,
    *,
    where_sql: str,
    order_sql: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            f"""
            WITH latest_assignment AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    occurred_at AS assigned_at,
                    DATE(occurred_at) AS allotment_date
                FROM workflow_events
                WHERE event_type = 'claim_assigned'
                ORDER BY claim_id, occurred_at DESC
            ),
            doc_stats AS (
                SELECT
                    cd.claim_id,
                    COUNT(*) AS documents,
                    SUM(
                        CASE
                            WHEN (cd.metadata->>'merge_source_file_count') ~ '^[0-9]+$'
                                AND CAST(cd.metadata->>'merge_source_file_count' AS INTEGER) > 0
                                THEN CAST(cd.metadata->>'merge_source_file_count' AS INTEGER)
                            WHEN (cd.metadata->>'merge_accepted_file_count') ~ '^[0-9]+$'
                                AND CAST(cd.metadata->>'merge_accepted_file_count' AS INTEGER) > 0
                                THEN CAST(cd.metadata->>'merge_accepted_file_count' AS INTEGER)
                            ELSE 1
                        END
                    ) AS source_files,
                    MAX(cd.uploaded_at) AS last_upload,
                    (
                        ARRAY_REMOVE(
                            ARRAY_AGG(NULLIF(TRIM(COALESCE(cd.uploaded_by, '')), '') ORDER BY cd.uploaded_at DESC NULLS LAST),
                            NULL
                        )
                    )[1] AS last_uploaded_by
                FROM claim_documents cd
                GROUP BY cd.claim_id
            ),
            latest_report AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    export_uri
                FROM report_versions
                ORDER BY claim_id, version_no DESC
            ),
            upload_meta AS (
                SELECT
                    claim_id,
                    report_export_status,
                    tagging,
                    subtagging,
                    opinion
                FROM claim_report_uploads
            ),
            latest_decision AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    recommendation,
                    explanation_summary,
                    generated_at
                FROM decision_results
                WHERE is_active = TRUE
                ORDER BY claim_id, generated_at DESC
            ),
            latest_auditor_learning AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    NULLIF(TRIM(COALESCE(notes, '')), '') AS learning_note
                FROM feedback_labels
                WHERE LOWER(TRIM(label_type)) = 'auditor_report_learning'
                ORDER BY claim_id, created_at DESC
            ),
            legacy_data AS (
                SELECT claim_id, legacy_payload
                FROM claim_legacy_data
            )
            SELECT
                c.id,
                c.external_claim_id,
                c.assigned_doctor_id,
                c.tags,
                c.status,
                CASE
                    WHEN c.status = 'waiting_for_documents' AND COALESCE(ds.documents, 0) > 0 THEN 'pending'
                    ELSE c.status::text
                END AS status_display,
                la.assigned_at,
                la.allotment_date,
                COALESCE(ds.documents, 0) AS documents,
                COALESCE(ds.source_files, 0) AS source_files,
                ds.last_upload,
                COALESCE(ds.last_uploaded_by, '') AS last_uploaded_by,
                COALESCE(NULLIF(TRIM(ld.explanation_summary), ''), COALESCE(ld.recommendation::text, 'Pending')) AS final_status,
                COALESCE(
                    NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'doa_date', '')), ''),
                    NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'doa', '')), ''),
                    NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'doa date', '')), ''),
                    NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'date_of_admission', '')), ''),
                    NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'date of admission', '')), ''),
                    NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'admission_date', '')), ''),
                    NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'admission date', '')), '')
                ) AS doa_date,
                COALESCE(
                    NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'dod_date', '')), ''),
                    NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'dod', '')), ''),
                    NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'dod date', '')), ''),
                    NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'date_of_discharge', '')), ''),
                    NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'date of discharge', '')), ''),
                    NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'discharge_date', '')), ''),
                    NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'discharge date', '')), '')
                ) AS dod_date,
                COALESCE(al.learning_note, '') AS auditor_learning,
                ldata.legacy_payload AS legacy_payload
            FROM claims c
            LEFT JOIN latest_assignment la ON la.claim_id = c.id
            LEFT JOIN doc_stats ds ON ds.claim_id = c.id
            LEFT JOIN latest_report rv ON rv.claim_id = c.id
            LEFT JOIN upload_meta um ON um.claim_id = c.id
            LEFT JOIN latest_decision ld ON ld.claim_id = c.id
            LEFT JOIN latest_auditor_learning al ON al.claim_id = c.id
            LEFT JOIN legacy_data ldata ON ldata.claim_id = c.id
            {where_sql}
            ORDER BY COALESCE(la.allotment_date, DATE(c.updated_at)) {order_sql}, c.updated_at {order_sql}
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()
    return [dict(r) for r in rows]


__all__ = ["count_claim_document_status", "list_claim_document_status_rows"]

