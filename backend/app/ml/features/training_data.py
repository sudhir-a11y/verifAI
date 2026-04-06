"""Training data collection — DB access to collect training rows."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def collect_training_rows(db: Session) -> list[dict[str, Any]]:
    """Collect training data by joining claims, extractions, feedback, and decisions."""
    rows = db.execute(
        text(
            """
            WITH latest_extraction AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    extracted_entities,
                    evidence_refs,
                    created_at
                FROM document_extractions
                ORDER BY claim_id, created_at DESC
            ),
            latest_feedback AS (
                SELECT
                    x.claim_id,
                    x.label_value,
                    x.label_type,
                    x.created_at
                FROM (
                    SELECT
                        claim_id,
                        LOWER(TRIM(label_value)) AS label_value,
                        LOWER(TRIM(label_type)) AS label_type,
                        created_at,
                        ROW_NUMBER() OVER (
                            PARTITION BY claim_id
                            ORDER BY
                                CASE
                                    WHEN LOWER(TRIM(label_type)) = 'auditor_qc_status' THEN 0
                                    WHEN LOWER(TRIM(label_type)) = 'hybrid_rule_ml' THEN 1
                                    WHEN LOWER(TRIM(label_type)) = 'extraction_html_alignment' THEN 2
                                    ELSE 3
                                END,
                                created_at DESC
                        ) AS rn
                    FROM feedback_labels
                ) x
                WHERE x.rn = 1
            ),
            latest_decision AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    rule_hits,
                    explanation_summary,
                    recommendation AS decision_recommendation,
                    route_target AS decision_route_target,
                    decision_payload,
                    generated_at
                FROM decision_results
                ORDER BY claim_id, generated_at DESC
            )
            SELECT
                c.id,
                c.external_claim_id,
                c.patient_name,
                c.patient_identifier,
                c.status,
                c.priority,
                c.source_channel,
                c.tags,
                le.extracted_entities,
                le.evidence_refs,
                ld.rule_hits,
                ld.explanation_summary,
                ld.decision_recommendation,
                ld.decision_route_target,
                ld.decision_payload,
                lf.label_type AS supervised_label_type,
                CASE
                    WHEN lf.label_value IN ('approve','approved') THEN 'approve'
                    WHEN lf.label_value IN ('reject','rejected') THEN 'reject'
                    WHEN lf.label_value IN ('need_more_evidence','query') THEN 'need_more_evidence'
                    WHEN lf.label_value IN ('manual_review','review') THEN 'manual_review'
                    WHEN c.status = 'completed' THEN 'approve'
                    WHEN c.status = 'withdrawn' THEN 'reject'
                    ELSE NULL
                END AS supervised_label
            FROM claims c
            LEFT JOIN latest_extraction le ON le.claim_id = c.id
            LEFT JOIN latest_feedback lf ON lf.claim_id = c.id
            LEFT JOIN latest_decision ld ON ld.claim_id = c.id
            """
        )
    ).mappings().all()
    return [dict(row) for row in rows]
