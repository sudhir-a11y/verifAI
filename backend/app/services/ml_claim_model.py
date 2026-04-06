"""Compatibility shim — all symbols now live in app.ml.

This module re-exports everything from app.ml for backward compatibility.
New code should import from app.ml directly.
"""

from app.ml import (
    ALLOWED_LABELS,
    AUDITOR_QC_LABEL_TYPE,
    HYBRID_LABEL_TYPE,
    MLPrediction,
    MODEL_KEY,
    ALIGNMENT_LABEL_TYPE,
    ensure_model,
    generate_alignment_feedback_labels,
    predict_claim_recommendation,
    recommendation_to_feedback_label,
    upsert_feedback_label,
)

__all__ = [
    "MLPrediction",
    "MODEL_KEY",
    "ALLOWED_LABELS",
    "ALIGNMENT_LABEL_TYPE",
    "HYBRID_LABEL_TYPE",
    "AUDITOR_QC_LABEL_TYPE",
    "ensure_model",
    "predict_claim_recommendation",
    "generate_alignment_feedback_labels",
    "upsert_feedback_label",
    "recommendation_to_feedback_label",
]
