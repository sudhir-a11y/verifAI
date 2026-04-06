"""Feedback labels — manual label upsert and recommendation-to-label mapping."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories import feedback_labels_repo

ALLOWED_LABELS = {"approve", "reject", "need_more_evidence", "manual_review"}


def recommendation_to_feedback_label(raw: str | None) -> str | None:
    """Map a recommendation string to a canonical feedback label."""
    recommendation = str(raw or "").strip().lower()
    if recommendation in {"approve", "approved", "admissible", "payable"}:
        return "approve"
    if recommendation in {"reject", "rejected", "inadmissible"}:
        return "reject"
    if recommendation in {"need_more_evidence", "query"}:
        return "need_more_evidence"
    if recommendation in {"manual_review", "in_review"}:
        return "manual_review"
    return None


def upsert_feedback_label(
    db: Session,
    *,
    claim_id: str,
    label_type: str,
    label_value: str,
    created_by: str,
    override_reason: str | None = None,
    notes: str | None = None,
    decision_id: str | None = None,
) -> bool:
    """Insert or replace a feedback label for a claim."""
    claim_key = str(claim_id or "").strip()
    label_type_key = str(label_type or "").strip().lower()
    label_value_key = str(label_value or "").strip().lower()
    if not claim_key or not label_type_key or label_value_key not in ALLOWED_LABELS:
        return False

    feedback_labels_repo.delete_feedback_labels(db, claim_id=claim_key, label_type=label_type_key)
    feedback_labels_repo.insert_feedback_label(
        db,
        claim_id=claim_key,
        decision_id=decision_id,
        label_type=label_type_key,
        label_value=label_value_key,
        override_reason=override_reason or "",
        notes=notes or "",
        created_by=created_by,
    )
    return True
