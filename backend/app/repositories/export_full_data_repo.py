from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def list_export_full_data_rows(
    db: Session,
    *,
    from_date: str | None,
    to_date: str | None,
    allotment_date: str | None,
) -> list[dict[str, Any]]:
    filters: list[str] = []
    params: dict[str, Any] = {}

    if from_date:
        filters.append("DATE(c.created_at) >= :from_date")
        params["from_date"] = from_date

    if to_date:
        filters.append("la.allotment_date <= :to_date")
        params["to_date"] = to_date

    if allotment_date:
        filters.append(
            "("
            "EXISTS ("
            "  SELECT 1 FROM workflow_events we "
            "  WHERE we.claim_id = c.id AND we.event_type = 'claim_assigned' AND DATE(we.occurred_at) = :allotment_date"
            ") OR "
            "CASE "
            "WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{4}-\\d{2}-\\d{2}$' "
            "THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD') "
            "WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}-\\d{2}-\\d{4}$' "
            "THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD-MM-YYYY') "
            "WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}/\\d{2}/\\d{4}$' "
            "THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD/MM/YYYY') "
            "ELSE NULL END = :allotment_date"
            ")"
        )
        params["allotment_date"] = allotment_date

    where_sql = ("WHERE " + " AND ".join(filters)) if filters else ""

    rows = db.execute(
        text(
            f"""
            WITH latest_report AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id, report_status, export_uri, version_no, created_at AS report_created_at
                FROM report_versions
                ORDER BY claim_id, version_no DESC
            ),
            latest_assignment AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    DATE(occurred_at) AS allotment_date
                FROM workflow_events
                WHERE event_type = 'claim_assigned'
                ORDER BY claim_id, occurred_at DESC
            ),
            doc_stats AS (
                SELECT claim_id, COUNT(*) AS documents
                FROM claim_documents
                GROUP BY claim_id
            ),
            latest_decision AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    explanation_summary
                FROM decision_results
                WHERE is_active = TRUE
                ORDER BY claim_id, generated_at DESC
            ),
            upload_meta AS (
                SELECT
                    claim_id,
                    report_export_status,
                    tagging,
                    subtagging,
                    opinion,
                    qc_status,
                    updated_by
                FROM claim_report_uploads
            ),
            legacy_data AS (
                SELECT claim_id, legacy_payload
                FROM claim_legacy_data
            )
            SELECT
                ROW_NUMBER() OVER (ORDER BY c.created_at DESC) AS row_id,
                c.external_claim_id,
                c.patient_name,
                c.patient_identifier,
                c.status,
                c.assigned_doctor_id,
                c.priority,
                c.source_channel,
                c.tags,
                c.created_at,
                c.updated_at,
                la.allotment_date,
                COALESCE(ds.documents, 0) AS documents,
                COALESCE(ldec.explanation_summary, '') AS trigger_remarks,
                COALESCE(rv.report_status, 'pending') AS report_status,
                COALESCE(rv.export_uri, '') AS export_uri,
                COALESCE(rv.version_no, 0) AS version_no,
                rv.report_created_at,
                COALESCE(um.report_export_status, CASE WHEN COALESCE(rv.export_uri, '') <> '' THEN 'uploaded' ELSE 'pending' END) AS report_export_status,
                COALESCE(um.tagging, '') AS tagging,
                COALESCE(um.subtagging, '') AS subtagging,
                COALESCE(um.opinion, '') AS opinion,
                CASE WHEN LOWER(REPLACE(REPLACE(COALESCE(um.qc_status, 'no'), ' ', '_'), '-', '_')) IN ('yes', 'qc_yes', 'qcyes', 'qc_done', 'done') THEN 'yes' ELSE 'no' END AS qc_status,
                COALESCE(um.updated_by, '') AS uploaded_by_username,
                u.id AS uploaded_by_user_id,
                ldata.legacy_payload
            FROM claims c
            LEFT JOIN latest_report rv ON rv.claim_id = c.id
            LEFT JOIN latest_assignment la ON la.claim_id = c.id
            LEFT JOIN doc_stats ds ON ds.claim_id = c.id
            LEFT JOIN latest_decision ldec ON ldec.claim_id = c.id
            LEFT JOIN upload_meta um ON um.claim_id = c.id
            LEFT JOIN users u ON u.username = um.updated_by
            LEFT JOIN legacy_data ldata ON ldata.claim_id = c.id
            {where_sql}
            ORDER BY c.created_at DESC
            """
        ),
        params,
    ).mappings().all()

    return [dict(row) for row in rows]

