from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.ml import ensure_model as _ensure_model
from app.ml import generate_alignment_feedback_labels as _generate_alignment_feedback_labels


def train_checklist_model(db: Session, *, force_retrain: bool) -> dict[str, Any] | None:
    model = _ensure_model(db=db, force_retrain=bool(force_retrain))
    return model if isinstance(model, dict) else None


def generate_alignment_labels(db: Session, *, created_by: str, overwrite: bool) -> dict[str, Any]:
    return _generate_alignment_feedback_labels(db=db, created_by=created_by, overwrite=bool(overwrite))

