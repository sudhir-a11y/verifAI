"""Final-decision ML model (Doctor + Auditor supervised).

Implements prompts/16_ML.md minimal stack:
  - dataset builder from existing DB tables
  - RandomForest training + artifact save
  - prediction helper used by /decide
"""

from app.ml_decision.predictor import (
    FinalDecisionMLPrediction,
    ensure_final_decision_model,
    predict_final_decision,
    train_final_decision_model,
)

__all__ = [
    "FinalDecisionMLPrediction",
    "ensure_final_decision_model",
    "predict_final_decision",
    "train_final_decision_model",
]

