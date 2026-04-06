from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_latest_decision_for_claim(db: Session, claim_id: UUID) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT id, recommendation
            FROM decision_results
            WHERE claim_id = :claim_id
            ORDER BY generated_at DESC
            LIMIT 1
            """
        ),
        {"claim_id": str(claim_id)},
    ).mappings().first()
    return dict(row) if row is not None else None


def delete_by_claim_id(db: Session, *, claim_id: str) -> int:
    return int(
        db.execute(text("DELETE FROM decision_results WHERE claim_id = :claim_id"), {"claim_id": claim_id}).rowcount or 0
    )


def _system_actor_expr(column_expr: str) -> str:
    col = f"LOWER(COALESCE({column_expr}, ''))"
    return (
        f"({col} LIKE 'system:%' OR {col} IN "
        "('system', 'system_ml', 'system-ai', 'ml-system', 'checklist_pipeline'))"
    )


def get_latest_decision_report_html_for_claim(db: Session, *, claim_id: UUID, source: str) -> dict[str, Any] | None:
    normalized_source = str(source or "any").strip().lower() or "any"
    if normalized_source not in {"any", "doctor", "system"}:
        raise ValueError("invalid source. allowed: any, doctor, system")

    system_expr = _system_actor_expr("dr.generated_by")
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
                0 AS version_no,
                NULLIF(TRIM(COALESCE(dr.decision_payload ->> 'report_html', '')), '') AS report_html,
                COALESCE(NULLIF(TRIM(COALESCE(dr.decision_payload ->> 'report_status', '')), ''), 'draft') AS report_status,
                COALESCE(dr.generated_by, '') AS created_by,
                CASE WHEN {system_expr} THEN 'system' ELSE 'doctor' END AS report_source,
                dr.generated_at AS created_at
            FROM claims c
            JOIN decision_results dr ON dr.claim_id = c.id
            WHERE c.id = :claim_id
              AND NULLIF(TRIM(COALESCE(dr.decision_payload ->> 'report_html', '')), '') IS NOT NULL
              {source_where}
            ORDER BY dr.generated_at DESC
            LIMIT 1
            """
        ),
        {"claim_id": str(claim_id)},
    ).mappings().first()
    return dict(row) if row is not None else None
