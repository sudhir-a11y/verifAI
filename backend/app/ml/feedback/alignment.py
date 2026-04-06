"""Alignment feedback — auto-generate labels by comparing extractions vs reports."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ml.features.extraction import (
    ALLOWED_LABELS,
    coerce_alignment_entities,
    evaluate_extraction_report_alignment,
)

ALIGNMENT_LABEL_TYPE = "extraction_html_alignment"


def generate_alignment_feedback_labels(
    db: Session,
    *,
    created_by: str = "system:ml_alignment",
    overwrite: bool = False,
) -> dict[str, int]:
    """Compare extracted entities against report HTML and insert alignment labels."""
    rows = db.execute(
        text(
            """
            WITH latest_extraction AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    extracted_entities,
                    created_at
                FROM document_extractions
                ORDER BY claim_id, created_at DESC
            ),
            latest_report_version AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    report_markdown AS report_html,
                    created_at
                FROM report_versions
                WHERE NULLIF(TRIM(COALESCE(report_markdown, '')), '') IS NOT NULL
                ORDER BY claim_id, version_no DESC, created_at DESC
            ),
            latest_decision_report AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    NULLIF(TRIM(COALESCE(decision_payload ->> 'report_html', '')), '') AS report_html,
                    NULLIF(TRIM(COALESCE(decision_payload ->> 'raw_response_json', '')), '') AS raw_response_json,
                    generated_at
                FROM decision_results
                WHERE NULLIF(TRIM(COALESCE(decision_payload ->> 'report_html', '')), '') IS NOT NULL
                ORDER BY claim_id, generated_at DESC
            )
            SELECT
                c.id,
                c.external_claim_id,
                le.extracted_entities,
                COALESCE(lrv.report_html, ldr.report_html) AS report_html,
                ldr.raw_response_json
            FROM claims c
            LEFT JOIN latest_extraction le ON le.claim_id = c.id
            LEFT JOIN latest_report_version lrv ON lrv.claim_id = c.id
            LEFT JOIN latest_decision_report ldr ON ldr.claim_id = c.id
            WHERE NULLIF(TRIM(COALESCE(lrv.report_html, ldr.report_html, '')), '') IS NOT NULL
            """
        )
    ).mappings().all()

    existing_rows = db.execute(
        text(
            """
            SELECT
                claim_id::text AS claim_id,
                SUM(CASE WHEN LOWER(TRIM(label_type)) = :alignment_label THEN 1 ELSE 0 END) AS alignment_count,
                SUM(CASE WHEN LOWER(TRIM(label_type)) <> :alignment_label THEN 1 ELSE 0 END) AS non_alignment_count
            FROM feedback_labels
            GROUP BY claim_id
            """
        ),
        {"alignment_label": ALIGNMENT_LABEL_TYPE},
    ).mappings().all()

    existing_map: dict[str, dict[str, int]] = {}
    for row in existing_rows:
        claim_id = str(row.get("claim_id") or "")
        if not claim_id:
            continue
        existing_map[claim_id] = {
            "alignment": int(row.get("alignment_count") or 0),
            "non_alignment": int(row.get("non_alignment_count") or 0),
        }

    inserted = 0
    skipped_existing = 0
    skipped_insufficient = 0

    for row in rows:
        claim_id = str(row.get("id") or "").strip()
        if not claim_id:
            continue

        existing = existing_map.get(claim_id, {"alignment": 0, "non_alignment": 0})
        if int(existing.get("non_alignment") or 0) > 0:
            skipped_existing += 1
            continue

        if int(existing.get("alignment") or 0) > 0:
            if overwrite:
                db.execute(
                    text(
                        """
                        DELETE FROM feedback_labels
                        WHERE claim_id = :claim_id AND LOWER(TRIM(label_type)) = :alignment_label
                        """
                    ),
                    {"claim_id": claim_id, "alignment_label": ALIGNMENT_LABEL_TYPE},
                )
            else:
                skipped_existing += 1
                continue

        extracted_entities = coerce_alignment_entities(row.get("extracted_entities"), row.get("raw_response_json"))
        report_html = str(row.get("report_html") or "")
        alignment = evaluate_extraction_report_alignment(extracted_entities, report_html)

        label = str(alignment.get("label") or "").strip().lower() or None
        if label not in ALLOWED_LABELS:
            skipped_insufficient += 1
            continue

        db.execute(
            text(
                """
                INSERT INTO feedback_labels (
                    claim_id,
                    decision_id,
                    label_type,
                    label_value,
                    override_reason,
                    notes,
                    created_by
                )
                VALUES (
                    :claim_id,
                    NULL,
                    :label_type,
                    :label_value,
                    :override_reason,
                    :notes,
                    :created_by
                )
                """
            ),
            {
                "claim_id": claim_id,
                "label_type": ALIGNMENT_LABEL_TYPE,
                "label_value": label,
                "override_reason": "auto_label_from_extraction_vs_report_html",
                "notes": json.dumps(
                    {
                        "score": round(float(alignment.get("score") or 0.0), 4),
                        "compared": int(alignment.get("compared") or 0),
                        "matched": int(alignment.get("matched") or 0),
                        "compared_fields": alignment.get("compared_fields") or [],
                        "matched_fields": alignment.get("matched_fields") or [],
                        "external_claim_id": str(row.get("external_claim_id") or ""),
                    },
                    ensure_ascii=False,
                ),
                "created_by": created_by,
            },
        )
        inserted += 1

    return {
        "processed": len(rows),
        "inserted": inserted,
        "skipped_existing": skipped_existing,
        "skipped_insufficient": skipped_insufficient,
    }
