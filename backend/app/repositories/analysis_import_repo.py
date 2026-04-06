"""Repository for analysis SQL dump import operations.

Bulk operations for legacy data import — no business logic.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def load_all_claim_ids(db: Session) -> dict[str, str]:
    """Load all claim external_id -> uuid mappings."""
    rows = db.execute(text("SELECT id::text AS id, external_claim_id FROM claims")).mappings().all()
    return {str(r.get("external_claim_id") or "").strip(): str(r.get("id") or "") for r in rows if r.get("external_claim_id")}


def load_decision_legacy_map(db: Session) -> dict[int, str]:
    """Load legacy_analysis_id -> decision_result_id mapping."""
    rows = db.execute(
        text(
            """
            SELECT legacy_analysis_id, id::text AS id
            FROM decision_results
            WHERE legacy_analysis_id IS NOT NULL
            """
        )
    ).mappings().all()
    out: dict[int, str] = {}
    for row in rows:
        try:
            out[int(row.get("legacy_analysis_id"))] = str(row.get("id") or "")
        except Exception:
            continue
    return out


def load_report_decision_map(db: Session) -> dict[str, str]:
    """Load decision_id -> report_version_id mapping."""
    rows = db.execute(
        text(
            """
            SELECT decision_id::text AS decision_id, id::text AS id
            FROM report_versions
            WHERE decision_id IS NOT NULL
            """
        )
    ).mappings().all()
    return {str(r.get("decision_id") or ""): str(r.get("id") or "") for r in rows if r.get("decision_id")}


def load_next_report_versions(db: Session) -> dict[str, int]:
    """Load next version number per claim."""
    rows = db.execute(
        text(
            """
            SELECT claim_id::text AS claim_id, COALESCE(MAX(version_no), 0) AS max_version
            FROM report_versions
            GROUP BY claim_id
            """
        )
    ).mappings().all()
    return {str(r.get("claim_id") or ""): int(r.get("max_version") or 0) + 1 for r in rows}


def update_decision_result(db: Session, decision_id: str, params: dict[str, Any]) -> str | None:
    """Update an existing decision result."""
    row = db.execute(
        text(
            """
            UPDATE decision_results
            SET
                claim_id = CAST(:claim_id AS uuid),
                model_version = :model_version,
                qc_risk_score = :qc_risk_score,
                consistency_checks = CAST(:consistency_checks AS jsonb),
                rule_hits = CAST(:rule_hits AS jsonb),
                explanation_summary = :explanation_summary,
                recommendation = :recommendation,
                route_target = :route_target,
                manual_review_required = :manual_review_required,
                review_priority = :review_priority,
                decision_payload = CAST(:decision_payload AS jsonb),
                generated_by = :generated_by,
                generated_at = COALESCE(:generated_at, generated_at)
            WHERE id = CAST(:id AS uuid)
            RETURNING id::text AS id
            """
        ),
        {**params, "id": decision_id},
    ).mappings().first()
    return str(row["id"]) if row and row.get("id") else None


def insert_or_upsert_decision_result(db: Session, params: dict[str, Any]) -> str:
    """Insert or upsert a decision result. Returns the decision id."""
    row = db.execute(
        text(
            """
            INSERT INTO decision_results (
                legacy_analysis_id,
                claim_id,
                rule_version,
                model_version,
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
                :legacy_analysis_id,
                CAST(:claim_id AS uuid),
                :rule_version,
                :model_version,
                :qc_risk_score,
                CAST(:consistency_checks AS jsonb),
                CAST(:rule_hits AS jsonb),
                :explanation_summary,
                :recommendation,
                :route_target,
                :manual_review_required,
                :review_priority,
                CAST(:decision_payload AS jsonb),
                :generated_by,
                COALESCE(:generated_at, NOW()),
                FALSE
            )
            ON CONFLICT (legacy_analysis_id)
            DO UPDATE SET
                claim_id = EXCLUDED.claim_id,
                model_version = EXCLUDED.model_version,
                qc_risk_score = EXCLUDED.qc_risk_score,
                consistency_checks = EXCLUDED.consistency_checks,
                rule_hits = EXCLUDED.rule_hits,
                explanation_summary = EXCLUDED.explanation_summary,
                recommendation = EXCLUDED.recommendation,
                route_target = EXCLUDED.route_target,
                manual_review_required = EXCLUDED.manual_review_required,
                review_priority = EXCLUDED.review_priority,
                decision_payload = EXCLUDED.decision_payload,
                generated_by = EXCLUDED.generated_by,
                generated_at = EXCLUDED.generated_at
            RETURNING id::text AS id
            """
        ),
        params,
    ).mappings().one()
    return str(row.get("id") or "")


def update_report_version(db: Session, report_id: str, params: dict[str, Any]) -> None:
    """Update an existing report version."""
    db.execute(
        text(
            """
            UPDATE report_versions
            SET report_markdown = :report_markdown,
                report_status = :report_status,
                created_by = :created_by,
                created_at = COALESCE(:created_at, created_at)
            WHERE id = CAST(:id AS uuid)
            """
        ),
        {**params, "id": report_id},
    )


def insert_report_version(db: Session, params: dict[str, Any]) -> str:
    """Insert a new report version. Returns the report id."""
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
                created_by,
                created_at
            )
            VALUES (
                CAST(:claim_id AS uuid),
                CAST(:decision_id AS uuid),
                :version_no,
                :report_status,
                :report_markdown,
                '',
                :created_by,
                COALESCE(:created_at, NOW())
            )
            RETURNING id::text AS id
            """
        ),
        params,
    ).mappings().one()
    return str(row.get("id") or "")
