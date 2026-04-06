"""ML layer — claim classification via Naive Bayes.

Public API (backward-compatible with app.services.ml_claim_model):
    - MLPrediction
    - MODEL_KEY
    - ALLOWED_LABELS
    - ALIGNMENT_LABEL_TYPE
    - HYBRID_LABEL_TYPE
    - AUDITOR_QC_LABEL_TYPE
    - ensure_model
    - predict_claim_recommendation
    - generate_alignment_feedback_labels
    - upsert_feedback_label
    - recommendation_to_feedback_label
"""

from app.ml.features.extraction import ALLOWED_LABELS
from app.ml.feedback.alignment import ALIGNMENT_LABEL_TYPE, generate_alignment_feedback_labels
from app.ml.feedback.labels import recommendation_to_feedback_label, upsert_feedback_label
from app.ml.inference.predictor import ensure_model, predict_claim_recommendation
from app.ml.models.naive_bayes import MLPrediction

# Constants re-exported for backward compatibility
MODEL_KEY = "claim_recommendation_nb"
HYBRID_LABEL_TYPE = "hybrid_rule_ml"
AUDITOR_QC_LABEL_TYPE = "auditor_qc_status"

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
