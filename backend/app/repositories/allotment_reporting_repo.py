from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def _system_actor_expr(column_expr: str) -> str:
    col = f"LOWER(COALESCE({column_expr}, ''))"
    return (
        f"({col} LIKE 'system:%' OR {col} IN "
        "('system', 'system_ml', 'system-ai', 'ml-system', 'checklist_pipeline'))"
    )


def list_allotment_date_wise_summary(
    db: Session,
    *,
    from_date: str | None,
    to_date: str | None,
) -> list[dict[str, Any]]:
    filters: list[str] = []
    params: dict[str, Any] = {}

    if from_date:
        filters.append("b.allotment_date >= :from_date")
        params["from_date"] = from_date
    if to_date:
        filters.append("b.allotment_date <= :to_date")
        params["to_date"] = to_date

    where_sql = ""
    if filters:
        where_sql = " AND " + " AND ".join(filters)

    system_report_expr = _system_actor_expr("created_by")

    rows = db.execute(
        text(
            f"""
            WITH latest_assignment AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    DATE(occurred_at) AS allotment_date
                FROM workflow_events
                WHERE event_type = 'claim_assigned'
                ORDER BY claim_id, occurred_at DESC
            ),
            latest_report AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    export_uri
                FROM report_versions
                ORDER BY claim_id, version_no DESC
            ),
            doctor_saved_reports AS (
                SELECT
                    claim_id,
                    1 AS has_doctor_saved
                FROM report_versions
                WHERE NULLIF(TRIM(COALESCE(report_markdown, '')), '') IS NOT NULL
                  AND NOT ({system_report_expr})
                GROUP BY claim_id
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
            legacy_data AS (
                SELECT
                    claim_id,
                    legacy_payload,
                    updated_at AS legacy_updated_at
                FROM claim_legacy_data
            ),
            base AS (
                SELECT
                    ldata.claim_id,
                    LOWER(TRIM(COALESCE(CAST(c.status AS TEXT), ''))) AS claim_status,
                    CASE WHEN NULLIF(TRIM(COALESCE(c.assigned_doctor_id, '')), '') IS NOT NULL THEN 1 ELSE 0 END AS is_allotted_to_doctor,
                    CASE WHEN COALESCE(dsr.has_doctor_saved, 0) = 1 THEN 1 ELSE 0 END AS has_doctor_saved,
                    COALESCE(
                        CASE
                            WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\d{{4}}-\d{{2}}-\d{{2}}$'
                                THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD')
                            WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\d{{4}}-\d{{2}}-\d{{2}}\s+\d{{2}}:\d{{2}}:\d{{2}}$'
                                THEN TO_TIMESTAMP(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD HH24:MI:SS')::date
                            WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\d{{2}}-\d{{2}}-\d{{4}}$'
                                THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD-MM-YYYY')
                            WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\d{{2}}/\d{{2}}/\d{{4}}$'
                                THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD/MM/YYYY')
                            ELSE NULL
                        END,
                        DATE(ldata.legacy_updated_at),
                        la.allotment_date,
                        DATE(c.updated_at)
                    ) AS allotment_date,
                    CASE
                        WHEN NULLIF(TRIM(COALESCE(um.tagging, '')), '') IS NOT NULL
                          OR NULLIF(TRIM(COALESCE(um.subtagging, '')), '') IS NOT NULL
                          OR NULLIF(TRIM(COALESCE(um.opinion, '')), '') IS NOT NULL
                          OR LOWER(TRIM(COALESCE(um.report_export_status, 'pending'))) = 'uploaded'
                          OR COALESCE(rv.export_uri, '') <> ''
                        THEN 1
                        ELSE 0
                    END AS is_uploaded
                FROM legacy_data ldata
                LEFT JOIN claims c ON c.id = ldata.claim_id
                LEFT JOIN latest_assignment la ON la.claim_id = ldata.claim_id
                LEFT JOIN upload_meta um ON um.claim_id = ldata.claim_id
                LEFT JOIN latest_report rv ON rv.claim_id = ldata.claim_id
                LEFT JOIN doctor_saved_reports dsr ON dsr.claim_id = ldata.claim_id
            )
            SELECT
                b.allotment_date,
                COUNT(*) FILTER (WHERE b.claim_status = 'completed' AND b.is_uploaded = 1) AS completed_count,
                COUNT(*) FILTER (WHERE b.is_allotted_to_doctor = 1 AND b.has_doctor_saved = 0) AS pending_count,
                COUNT(*) FILTER (WHERE b.claim_status = 'completed' AND b.is_uploaded = 1) AS uploaded_count,
                COUNT(*) AS total_count
            FROM base b
            WHERE b.allotment_date IS NOT NULL
            {where_sql}
            GROUP BY b.allotment_date
            ORDER BY b.allotment_date DESC
            """
        ),
        params,
    ).mappings().all()

    return [dict(r) for r in rows]


def list_allotment_date_wise_claims(
    db: Session,
    *,
    bucket: str,
    allotment_date: str | None,
    from_date: str | None,
    to_date: str | None,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, Any]]]:
    normalized_bucket = str(bucket or "all").strip().lower()
    if normalized_bucket not in {"all", "pending", "completed"}:
        normalized_bucket = "all"

    filters: list[str] = ["b.allotment_date IS NOT NULL"]
    params: dict[str, Any] = {"limit": int(limit), "offset": int(offset)}

    if allotment_date:
        filters.append("b.allotment_date = :allotment_date")
        params["allotment_date"] = allotment_date
    if from_date:
        filters.append("b.allotment_date >= :from_date")
        params["from_date"] = from_date
    if to_date:
        filters.append("b.allotment_date <= :to_date")
        params["to_date"] = to_date

    if normalized_bucket == "completed":
        filters.append("(b.claim_status = 'completed' AND b.is_uploaded = 1)")
    elif normalized_bucket == "pending":
        filters.append("b.is_allotted_to_doctor = 1 AND b.has_doctor_saved = 0")

    where_sql = "WHERE " + " AND ".join(filters)
    system_report_expr = _system_actor_expr("created_by")

    cte_sql = f"""
        WITH latest_assignment AS (
            SELECT DISTINCT ON (claim_id)
                claim_id,
                DATE(occurred_at) AS allotment_date
            FROM workflow_events
            WHERE event_type = 'claim_assigned'
            ORDER BY claim_id, occurred_at DESC
        ),
        latest_report AS (
            SELECT DISTINCT ON (claim_id)
                claim_id,
                export_uri
            FROM report_versions
            ORDER BY claim_id, version_no DESC
        ),
        doctor_saved_reports AS (
            SELECT
                claim_id,
                1 AS has_doctor_saved
            FROM report_versions
            WHERE NULLIF(TRIM(COALESCE(report_markdown, '')), '') IS NOT NULL
              AND NOT ({system_report_expr})
            GROUP BY claim_id
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
        legacy_data AS (
            SELECT
                claim_id,
                legacy_payload,
                updated_at AS legacy_updated_at
            FROM claim_legacy_data
        ),
        base AS (
            SELECT
                ldata.claim_id,
                COALESCE(c.external_claim_id, '') AS external_claim_id,
                COALESCE(c.patient_name, '') AS patient_name,
                COALESCE(c.assigned_doctor_id, '') AS assigned_doctor_id,
                LOWER(TRIM(COALESCE(CAST(c.status AS TEXT), ''))) AS claim_status,
                CASE WHEN NULLIF(TRIM(COALESCE(c.assigned_doctor_id, '')), '') IS NOT NULL THEN 1 ELSE 0 END AS is_allotted_to_doctor,
                CASE WHEN COALESCE(dsr.has_doctor_saved, 0) = 1 THEN 1 ELSE 0 END AS has_doctor_saved,
                COALESCE(
                    CASE
                        WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}$'
                            THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD')
                        WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}\\s+\\d{{2}}:\\d{{2}}:\\d{{2}}$'
                            THEN TO_TIMESTAMP(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD HH24:MI:SS')::date
                        WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{{2}}-\\d{{2}}-\\d{{4}}$'
                            THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD-MM-YYYY')
                        WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{{2}}/\\d{{2}}/\\d{{4}}$'
                            THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD/MM/YYYY')
                        ELSE NULL
                    END,
                    DATE(ldata.legacy_updated_at),
                    la.allotment_date,
                    DATE(c.updated_at)
                ) AS allotment_date,
                CASE
                    WHEN NULLIF(TRIM(COALESCE(um.tagging, '')), '') IS NOT NULL
                      OR NULLIF(TRIM(COALESCE(um.subtagging, '')), '') IS NOT NULL
                      OR NULLIF(TRIM(COALESCE(um.opinion, '')), '') IS NOT NULL
                      OR LOWER(TRIM(COALESCE(um.report_export_status, 'pending'))) = 'uploaded'
                      OR COALESCE(rv.export_uri, '') <> ''
                    THEN 1
                    ELSE 0
                END AS is_uploaded
            FROM legacy_data ldata
            LEFT JOIN claims c ON c.id = ldata.claim_id
            LEFT JOIN latest_assignment la ON la.claim_id = ldata.claim_id
            LEFT JOIN upload_meta um ON um.claim_id = ldata.claim_id
            LEFT JOIN latest_report rv ON rv.claim_id = ldata.claim_id
            LEFT JOIN doctor_saved_reports dsr ON dsr.claim_id = ldata.claim_id
        )
    """

    total = db.execute(
        text(
            f"""
            {cte_sql}
            SELECT COUNT(*)
            FROM base b
            {where_sql}
            """
        ),
        params,
    ).scalar_one()

    rows = db.execute(
        text(
            f"""
            {cte_sql}
            SELECT
                b.claim_id,
                b.external_claim_id,
                b.patient_name,
                b.assigned_doctor_id,
                b.claim_status,
                b.allotment_date,
                CASE
                    WHEN b.is_allotted_to_doctor = 1 AND b.has_doctor_saved = 0 THEN 'pending'
                    WHEN b.claim_status = 'completed' AND b.is_uploaded = 1 THEN 'completed'
                    ELSE 'other'
                END AS bucket
            FROM base b
            {where_sql}
            ORDER BY b.allotment_date DESC, b.external_claim_id ASC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()

    return int(total or 0), [dict(r) for r in rows]
