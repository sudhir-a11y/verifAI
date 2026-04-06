from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def next_version_no(db: Session, claim_id: UUID) -> int:
    value = db.execute(
        text("SELECT COALESCE(MAX(version_no), 0) + 1 FROM report_versions WHERE claim_id = :claim_id"),
        {"claim_id": str(claim_id)},
    ).scalar_one()
    return int(value or 1)


def insert_report_version(
    db: Session,
    *,
    claim_id: UUID,
    decision_id: UUID | None,
    version_no: int,
    report_status: str,
    report_markdown: str,
    created_by: str,
) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            INSERT INTO report_versions (
                claim_id,
                decision_id,
                version_no,
                report_status,
                report_markdown,
                export_uri,
                created_by
            )
            VALUES (
                :claim_id,
                :decision_id,
                :version_no,
                :report_status,
                :report_markdown,
                '',
                :created_by
            )
            RETURNING id, claim_id, decision_id, version_no, report_status, created_by, created_at
            """
        ),
        {
            "claim_id": str(claim_id),
            "decision_id": str(decision_id) if decision_id else None,
            "version_no": int(version_no),
            "report_status": report_status,
            "report_markdown": report_markdown,
            "created_by": created_by,
        },
    ).mappings().one()
    return dict(row)


def delete_by_claim_id(db: Session, *, claim_id: str) -> int:
    return int(
        db.execute(text("DELETE FROM report_versions WHERE claim_id = :claim_id"), {"claim_id": claim_id}).rowcount or 0
    )


def _system_actor_expr(column_expr: str) -> str:
    col = f"LOWER(COALESCE({column_expr}, ''))"
    return (
        f"({col} LIKE 'system:%' OR {col} IN "
        "('system', 'system_ml', 'system-ai', 'ml-system', 'checklist_pipeline'))"
    )


def get_latest_report_html_for_claim(db: Session, *, claim_id: UUID, source: str) -> dict[str, Any] | None:
    normalized_source = str(source or "any").strip().lower() or "any"
    if normalized_source not in {"any", "doctor", "system"}:
        raise ValueError("invalid source. allowed: any, doctor, system")

    system_expr = _system_actor_expr("rv.created_by")
    source_where = ""
    if normalized_source == "doctor":
        source_where = f" AND NOT ({system_expr})"
    elif normalized_source == "system":
        source_where = f" AND {system_expr}"

    row = db.execute(
        text(
            f"""
            SELECT
                c.id AS claim_id,
                c.external_claim_id,
                rv.version_no,
                COALESCE(rv.report_markdown, '') AS report_html,
                COALESCE(rv.report_status, 'draft') AS report_status,
                COALESCE(rv.created_by, '') AS created_by,
                CASE WHEN {system_expr} THEN 'system' ELSE 'doctor' END AS report_source,
                rv.created_at
            FROM claims c
            JOIN report_versions rv ON rv.claim_id = c.id
            WHERE c.id = :claim_id
              AND NULLIF(TRIM(COALESCE(rv.report_markdown, '')), '') IS NOT NULL
            {source_where}
            ORDER BY rv.version_no DESC
            LIMIT 1
            """
        ),
        {"claim_id": str(claim_id)},
    ).mappings().first()
    return dict(row) if row is not None else None
