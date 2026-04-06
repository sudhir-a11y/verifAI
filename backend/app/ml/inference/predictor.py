"""Prediction entry point — model loading, caching, training orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.ml.features.extraction import build_claim_text, extract_label
from app.ml.features.training_data import collect_training_rows
from app.ml.feedback.alignment import generate_alignment_feedback_labels
from app.ml.models.naive_bayes import MLPrediction, predict, train_naive_bayes
from app.ml.registry.model_registry import (
    MODEL_VERSION_PREFIX,
    load_latest_from_registry,
    persist_registry,
    write_artifact,
)

_MODEL_CACHE: dict[str, Any] | None = None


def _train_and_persist(db: Session) -> dict[str, Any] | None:
    """Train a new model from current DB data and persist it."""
    try:
        generate_alignment_feedback_labels(db=db, created_by="system:ml_alignment", overwrite=False)
    except Exception:
        # Alignment-label generation should not block model training.
        pass

    rows = collect_training_rows(db)
    examples: list[tuple[str, str]] = []
    for row in rows:
        label = extract_label(row)
        if label is None:
            continue
        text_value = build_claim_text(row)
        if not text_value.strip():
            continue
        examples.append((text_value, label))

    model = train_naive_bayes(examples)
    if not isinstance(model, dict):
        return None

    version = f"{MODEL_VERSION_PREFIX}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    model["version"] = version
    artifact_uri = write_artifact(model, version)
    persist_registry(db, version, artifact_uri, model)
    db.commit()
    return model


def ensure_model(db: Session, force_retrain: bool = False) -> dict[str, Any] | None:
    """Get the current model, training one if none exists."""
    global _MODEL_CACHE

    if force_retrain:
        model = _train_and_persist(db)
        _MODEL_CACHE = model
        return model

    if isinstance(_MODEL_CACHE, dict):
        return _MODEL_CACHE

    model = load_latest_from_registry(db)
    if not isinstance(model, dict):
        model = _train_and_persist(db)
    else:
        version = str(model.get("version") or "")
        if not version.startswith(MODEL_VERSION_PREFIX):
            retrained = _train_and_persist(db)
            if isinstance(retrained, dict):
                model = retrained

    _MODEL_CACHE = model
    return model


def predict_claim_recommendation(
    db: Session,
    claim_text: str,
    force_retrain: bool = False,
) -> MLPrediction:
    """Entry point: predict claim recommendation."""
    model = ensure_model(db, force_retrain=force_retrain)
    if not isinstance(model, dict):
        return MLPrediction(available=False, reason="model unavailable")

    pred = predict(model, claim_text)
    if pred.available:
        pred.model_version = str(model.get("version") or pred.model_version or "")
        pred.training_examples = int(model.get("num_examples") or pred.training_examples or 0)
    return pred
