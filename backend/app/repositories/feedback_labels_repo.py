from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def delete_feedback_labels(db: Session, *, claim_id: UUID, label_type: str) -> None:
    db.execute(
        text(
            """
            DELETE FROM feedback_labels
            WHERE claim_id = :claim_id AND label_type = :label_type
            """
        ),
        {"claim_id": str(claim_id), "label_type": str(label_type)},
    )


def insert_feedback_label(
    db: Session,
    *,
    claim_id: UUID,
    decision_id: UUID | None,
    label_type: str,
    label_value: str,
    override_reason: str,
    notes: str,
    created_by: str,
) -> None:
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
                :decision_id,
                :label_type,
                :label_value,
                :override_reason,
                :notes,
                :created_by
            )
            """
        ),
        {
            "claim_id": str(claim_id),
            "decision_id": str(decision_id) if decision_id else None,
            "label_type": str(label_type),
            "label_value": str(label_value),
            "override_reason": str(override_reason),
            "notes": str(notes),
            "created_by": str(created_by),
        },
    )


def delete_by_claim_id(db: Session, *, claim_id: str) -> int:
    return int(
        db.execute(text("DELETE FROM feedback_labels WHERE claim_id = :claim_id"), {"claim_id": str(claim_id)}).rowcount
        or 0
    )


def insert_label_raw(db: Session, params: dict[str, Any]) -> None:
    """Insert a feedback label using raw params dict (for ML alignment)."""
    db.execute(
        text(
            """
            INSERT INTO feedback_labels (
                claim_id, decision_id, label_type, label_value,
                override_reason, notes, created_by
            ) VALUES (
                :claim_id, :decision_id, :label_type, :label_value,
                :override_reason, :notes, :created_by
            )
            """
        ),
        params,
    )


def count_by_claim_and_type(db: Session, claim_id: str, label_type: str) -> dict[str, int]:
    """Count alignment vs non-alignment labels for a claim."""
    row = db.execute(
        text(
            """
            SELECT
                SUM(CASE WHEN LOWER(TRIM(label_type)) = :alignment_label THEN 1 ELSE 0 END) AS alignment_count,
                SUM(CASE WHEN LOWER(TRIM(label_type)) <> :alignment_label THEN 1 ELSE 0 END) AS non_alignment_count
            FROM feedback_labels
            WHERE claim_id = :claim_id
            """
        ),
        {"claim_id": claim_id, "alignment_label": label_type},
    ).mappings().first()
    return {
        "alignment": int(row.get("alignment_count") or 0) if row else 0,
        "non_alignment": int(row.get("non_alignment_count") or 0) if row else 0,
    }
