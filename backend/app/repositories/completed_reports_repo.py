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


def _qc_expr(column_expr: str = "um.qc_status") -> str:
    return (
        "CASE WHEN LOWER(REPLACE(REPLACE(COALESCE("
        + column_expr
        + ", 'no'), ' ', '_'), '-', '_')) IN "
        "('yes', 'qc_yes', 'qcyes', 'qc_done', 'done') THEN 'yes' ELSE 'no' END"
    )


def _allotment_date_expr() -> str:
    return (
        "COALESCE(la.allotment_date, "
        "CASE "
        "WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{4}-\\d{2}-\\d{2}$' "
        "THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD') "
        "WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}-\\d{2}-\\d{4}$' "
        "THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD-MM-YYYY') "
        "WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}/\\d{2}/\\d{4}$' "
        "THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD/MM/YYYY') "
        "ELSE NULL END)"
    )


def _effective_status_expr() -> str:
    return """CASE
        WHEN NULLIF(TRIM(COALESCE(um.tagging, '')), '') IS NOT NULL
             OR NULLIF(TRIM(COALESCE(um.subtagging, '')), '') IS NOT NULL
             OR NULLIF(TRIM(COALESCE(um.opinion, '')), '') IS NOT NULL
        THEN 'uploaded'
        WHEN COALESCE(um.report_export_status, 'pending') = 'uploaded'
        THEN 'uploaded'
        WHEN COALESCE(rv.export_uri, '') <> ''
        THEN 'uploaded'
        ELSE 'pending'
    END"""


def _build_filters(
    *,
    search_claim: str | None,
    allotment_date: str | None,
    doctor_tokens: list[str],
) -> tuple[list[str], dict[str, Any]]:
    filters: list[str] = ["c.status = 'completed'"]
    params: dict[str, Any] = {}

    if search_claim and str(search_claim).strip():
        filters.append("LOWER(c.external_claim_id) LIKE :search_claim")
        params["search_claim"] = f"%{str(search_claim).strip().lower()}%"

    if allotment_date:
        filters.append(f"{_allotment_date_expr()} = :allotment_date")
        params["allotment_date"] = allotment_date

    if doctor_tokens:
        doctor_clauses: list[str] = []
        for idx, doctor in enumerate(doctor_tokens):
            key = f"doctor_{idx}"
            params[key] = doctor
            doctor_clauses.append(
                f":{key} = ANY(string_to_array(regexp_replace(LOWER(COALESCE(c.assigned_doctor_id, '')), '[^a-z0-9,]+', '', 'g'), ','))"
            )
        filters.append("(" + " OR ".join(doctor_clauses) + ")")

    return filters, params


def count_completed_reports(
    db: Session,
    *,
    search_claim: str | None,
    allotment_date: str | None,
    doctor_tokens: list[str],
    status_filter: str,
    qc_filter: str,
    exclude_tagged: bool,
) -> int:
    filters, params = _build_filters(
        search_claim=search_claim,
        allotment_date=allotment_date,
        doctor_tokens=doctor_tokens,
    )

    where_sql = "WHERE " + " AND ".join(filters)
    status_where = ""
    if status_filter != "all":
        status_where = f" AND {_effective_status_expr()} = :status_filter"
        params["status_filter"] = status_filter

    qc_where = ""
    if qc_filter != "all":
        qc_where = f" AND {_qc_expr()} = :qc_filter"
        params["qc_filter"] = qc_filter

    tagged_where = ""
    if exclude_tagged:
        tagged_where = " AND NULLIF(TRIM(COALESCE(um.tagging, '')), '') IS NULL"

    total = db.execute(
        text(
            f"""
            WITH latest_report AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id, report_status, report_markdown, export_uri, version_no, created_at, created_by
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
            upload_meta AS (
                SELECT
                    claim_id,
                    report_export_status,
                    tagging,
                    subtagging,
                    opinion,
                    qc_status,
                    updated_at
                FROM claim_report_uploads
            ),
            legacy_data AS (
                SELECT claim_id, legacy_payload
                FROM claim_legacy_data
            )
            SELECT COUNT(*)
            FROM claims c
            LEFT JOIN latest_report rv ON rv.claim_id = c.id
            LEFT JOIN latest_assignment la ON la.claim_id = c.id
            LEFT JOIN upload_meta um ON um.claim_id = c.id
            LEFT JOIN legacy_data ldata ON ldata.claim_id = c.id
            {where_sql}
            {status_where}
            {qc_where}
            {tagged_where}
            """
        ),
        params,
    ).scalar_one()
    return int(total or 0)


def list_completed_reports(
    db: Session,
    *,
    search_claim: str | None,
    allotment_date: str | None,
    doctor_tokens: list[str],
    status_filter: str,
    qc_filter: str,
    exclude_tagged: bool,
    sort_order: str,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    normalized_sort = str(sort_order or "updated_desc").strip().lower()
    if normalized_sort not in {"updated_desc", "allotment_asc"}:
        normalized_sort = "updated_desc"

    allotment_date_expr = _allotment_date_expr()
    if normalized_sort == "allotment_asc":
        order_by_sql = (
            f"CASE WHEN {allotment_date_expr} IS NULL THEN 1 ELSE 0 END ASC, "
            f"{allotment_date_expr} ASC, c.updated_at ASC"
        )
    else:
        order_by_sql = "c.updated_at DESC"

    filters, params = _build_filters(
        search_claim=search_claim,
        allotment_date=allotment_date,
        doctor_tokens=doctor_tokens,
    )
    params.update({"limit": int(limit), "offset": int(offset)})

    where_sql = "WHERE " + " AND ".join(filters)
    status_where = ""
    if status_filter != "all":
        status_where = f" AND {_effective_status_expr()} = :status_filter"
        params["status_filter"] = status_filter

    qc_where = ""
    if qc_filter != "all":
        qc_where = f" AND {_qc_expr()} = :qc_filter"
        params["qc_filter"] = qc_filter

    tagged_where = ""
    if exclude_tagged:
        tagged_where = " AND NULLIF(TRIM(COALESCE(um.tagging, '')), '') IS NULL"

    system_report_expr_latest = _system_actor_expr("rv.created_by")
    system_report_expr_stats = _system_actor_expr("created_by")

    rows = db.execute(
        text(
            f"""
            WITH latest_report AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id, report_status, report_markdown, export_uri, version_no, created_at, created_by
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
            report_counts AS (
                SELECT claim_id, COUNT(*) AS report_count
                FROM report_versions
                GROUP BY claim_id
            ),
            report_source_stats AS (
                SELECT
                    claim_id,
                    MAX(CASE WHEN {system_report_expr_stats} THEN 1 ELSE 0 END) AS has_system_html,
                    MAX(CASE WHEN NOT ({system_report_expr_stats}) THEN 1 ELSE 0 END) AS has_doctor_html
                FROM report_versions
                WHERE NULLIF(TRIM(COALESCE(report_markdown, '')), '') IS NOT NULL
                GROUP BY claim_id
            ),
            upload_meta AS (
                SELECT
                    claim_id,
                    report_export_status,
                    tagging,
                    subtagging,
                    opinion,
                    qc_status,
                    updated_at
                FROM claim_report_uploads
            ),
            legacy_data AS (
                SELECT claim_id, legacy_payload
                FROM claim_legacy_data
            )
            SELECT
                c.id,
                c.external_claim_id,
                c.patient_name,
                c.assigned_doctor_id,
                c.updated_at,
                c.updated_at AS completed_at,
                {allotment_date_expr} AS allotment_date,
                COALESCE(rv.report_status, 'pending') AS report_status,
                COALESCE(rv.export_uri, '') AS export_uri,
                rv.created_at AS report_created_at,
                COALESCE(rv.version_no, 0) AS report_version,
                CASE WHEN NULLIF(TRIM(COALESCE(rv.report_markdown, '')), '') IS NULL THEN FALSE ELSE TRUE END AS report_html_available,
                CASE WHEN {system_report_expr_latest} THEN 'system' ELSE 'doctor' END AS latest_report_source,
                CASE WHEN COALESCE(rss.has_doctor_html, 0) = 1 THEN TRUE ELSE FALSE END AS doctor_report_html_available,
                CASE WHEN COALESCE(rss.has_system_html, 0) = 1 THEN TRUE ELSE FALSE END AS system_report_html_available,
                COALESCE(um.report_export_status, 'pending') AS stored_report_export_status,
                COALESCE(um.tagging, '') AS tagging,
                COALESCE(um.subtagging, '') AS subtagging,
                COALESCE(um.opinion, '') AS opinion,
                {_qc_expr()} AS qc_status,
                um.updated_at AS upload_updated_at,
                COALESCE(rc.report_count, 0) AS report_count,
                {_effective_status_expr()} AS effective_report_status
            FROM claims c
            LEFT JOIN latest_report rv ON rv.claim_id = c.id
            LEFT JOIN latest_assignment la ON la.claim_id = c.id
            LEFT JOIN report_counts rc ON rc.claim_id = c.id
            LEFT JOIN report_source_stats rss ON rss.claim_id = c.id
            LEFT JOIN upload_meta um ON um.claim_id = c.id
            LEFT JOIN legacy_data ldata ON ldata.claim_id = c.id
            {where_sql}
            {status_where}
            {qc_where}
            {tagged_where}
            ORDER BY {order_by_sql}
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()
    return [dict(r) for r in rows]


__all__ = ["count_completed_reports", "list_completed_reports"]

