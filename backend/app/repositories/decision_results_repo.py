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


def get_latest_decision_meta_for_claim(db: Session, claim_id: UUID) -> dict[str, Any] | None:
    """Return latest decision metadata used for routing/advancing workflow."""
    row = db.execute(
        text(
            """
            SELECT
                id,
                recommendation,
                route_target,
                manual_review_required,
                review_priority,
                explanation_summary,
                generated_by,
                generated_at
            FROM decision_results
            WHERE claim_id = :claim_id
            ORDER BY generated_at DESC
            LIMIT 1
            """
        ),
        {"claim_id": str(claim_id)},
    ).mappings().first()
    return dict(row) if row is not None else None


def get_latest_decision_row_for_claim(db: Session, claim_id: UUID) -> dict[str, Any] | None:
    """Return latest decision row including decision_payload for downstream generators."""
    row = db.execute(
        text(
            """
            SELECT
                id,
                recommendation,
                route_target,
                manual_review_required,
                review_priority,
                explanation_summary,
                decision_payload,
                generated_by,
                generated_at
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

def deactivate_active_for_claim(db: Session, *, claim_id: str) -> None:
    db.execute(
        text(
            """
            UPDATE decision_results
            SET is_active = FALSE
            WHERE claim_id = :claim_id AND is_active = TRUE
            """
        ),
        {"claim_id": str(claim_id)},
    )


def set_latest_route_target(db: Session, *, claim_id: str, route_target: str) -> None:
    """Update route_target on the latest decision_result row for a claim."""
    db.execute(
        text(
            """
            UPDATE decision_results
            SET route_target = :route_target
            WHERE id = (
                SELECT id
                FROM decision_results
                WHERE claim_id = :claim_id
                ORDER BY generated_at DESC
                LIMIT 1
            )
            """
        ),
        {"claim_id": str(claim_id), "route_target": str(route_target or "")[:120]},
    )


def insert_integration_decision_result(
    db: Session,
    *,
    claim_id: str,
    actor_id: str,
    recommendation: str,
    route_target: str,
    manual_review_required: bool,
    review_priority: int,
    explanation_summary: str | None,
    decision_payload: dict[str, Any],
    occurred_at: Any,
) -> str:
    import json

    row = db.execute(
        text(
            """
            INSERT INTO decision_results (
                claim_id,
                extraction_id,
                rule_version,
                model_version,
                fraud_risk_score,
                qc_risk_score,
                consistency_checks,
                rule_hits,
                explanation_summary,
                recommendation,
                route_target,
                manual_review_required,
                review_priority,
                decision_payload,
                generated_by,
                generated_at,
                is_active
            )
            VALUES (
                :claim_id,
                NULL,
                :rule_version,
                :model_version,
                NULL,
                NULL,
                CAST(:consistency_checks AS jsonb),
                CAST(:rule_hits AS jsonb),
                :explanation_summary,
                CAST(:recommendation AS decision_recommendation),
                :route_target,
                :manual_review_required,
                :review_priority,
                CAST(:decision_payload AS jsonb),
                :generated_by,
                COALESCE(:generated_at, NOW()),
                TRUE
            )
            RETURNING id
            """
        ),
        {
            "claim_id": str(claim_id),
            "rule_version": "integration_teamrightworks_v1",
            "model_version": "integration_external",
            "consistency_checks": "[]",
            "rule_hits": "[]",
            "explanation_summary": explanation_summary,
            "recommendation": recommendation,
            "route_target": route_target,
            "manual_review_required": bool(manual_review_required),
            "review_priority": int(review_priority),
            "decision_payload": json.dumps(decision_payload or {}),
            "generated_by": str(actor_id or ""),
            "generated_at": occurred_at,
        },
    ).mappings().one()
    return str(row.get("id") or "") or ""


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


def insert_decision_result(db: Session, params: dict[str, Any]) -> None:
    """Insert a decision result."""
    db.execute(
        text(
            """
            INSERT INTO decision_results (
                claim_id, recommendation, route_target, rule_hits,
                explanation_summary, decision_payload, generated_by, generated_at
            ) VALUES (
                :claim_id, :recommendation, :route_target,
                CAST(:rule_hits AS jsonb), :explanation_summary,
                CAST(:decision_payload AS jsonb), :generated_by, NOW()
            )
            """
        ),
        params,
    )


def update_decision_analysis(db: Session, decision_id: str, analysis: dict[str, Any]) -> None:
    """Update the legacy_analysis_id on a decision result."""
    db.execute(
        text(
            "UPDATE decision_results SET legacy_analysis_id = :analysis_id WHERE id = :decision_id"
        ),
        {"analysis_id": analysis.get("id"), "decision_id": decision_id},
    )


def get_decision_by_legacy_analysis_id(db: Session, legacy_analysis_id: str) -> dict[str, Any] | None:
    """Find a decision result by legacy_analysis_id."""
    row = db.execute(
        text(
            "SELECT id, claim_id FROM decision_results WHERE legacy_analysis_id = :legacy_analysis_id LIMIT 1"
        ),
        {"legacy_analysis_id": legacy_analysis_id},
    ).mappings().first()
    return dict(row) if row else None


def deactivate_active_checklist_pipeline_for_claim(db: Session, *, claim_id: UUID) -> None:
    db.execute(
        text(
            """
            UPDATE decision_results
            SET is_active = FALSE
            WHERE claim_id = :claim_id AND is_active = TRUE AND generated_by = 'checklist_pipeline'
            """
        ),
        {"claim_id": str(claim_id)},
    )


def insert_checklist_pipeline_decision_result(
    db: Session,
    *,
    claim_id: UUID,
    extraction_id: UUID | None,
    rule_version: str,
    model_version: str | None,
    fraud_risk_score: float | None,
    qc_risk_score: float | None,
    consistency_checks_json: str,
    rule_hits_json: str,
    explanation_summary: str,
    recommendation: str,
    route_target: str,
    manual_review_required: bool,
    review_priority: int,
    decision_payload_json: str,
) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            INSERT INTO decision_results (
                claim_id,
                extraction_id,
                rule_version,
                model_version,
                fraud_risk_score,
                qc_risk_score,
                consistency_checks,
                rule_hits,
                explanation_summary,
                recommendation,
                route_target,
                manual_review_required,
                review_priority,
                decision_payload,
                generated_by,
                is_active
            )
            VALUES (
                :claim_id,
                :extraction_id,
                :rule_version,
                :model_version,
                :fraud_risk_score,
                :qc_risk_score,
                CAST(:consistency_checks AS jsonb),
                CAST(:rule_hits AS jsonb),
                :explanation_summary,
                :recommendation,
                :route_target,
                :manual_review_required,
                :review_priority,
                CAST(:decision_payload AS jsonb),
                'checklist_pipeline',
                TRUE
            )
            RETURNING id, generated_at
            """
        ),
        {
            "claim_id": str(claim_id),
            "extraction_id": str(extraction_id) if extraction_id else None,
            "rule_version": rule_version,
            "model_version": model_version,
            "fraud_risk_score": fraud_risk_score,
            "qc_risk_score": qc_risk_score,
            "consistency_checks": consistency_checks_json,
            "rule_hits": rule_hits_json,
            "explanation_summary": explanation_summary,
            "recommendation": recommendation,
            "route_target": route_target,
            "manual_review_required": bool(manual_review_required),
            "review_priority": int(review_priority),
            "decision_payload": decision_payload_json,
        },
    ).mappings().one()
    return dict(row)


def get_latest_checklist_pipeline_decision_row(
    db: Session,
    *,
    claim_id: UUID,
) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT id, recommendation, route_target, manual_review_required, review_priority, generated_at, decision_payload
            FROM decision_results
            WHERE claim_id = :claim_id AND generated_by = 'checklist_pipeline'
            ORDER BY generated_at DESC
            LIMIT 1
            """
        ),
        {"claim_id": str(claim_id)},
    ).mappings().first()
    return dict(row) if row is not None else None
