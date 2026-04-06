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
