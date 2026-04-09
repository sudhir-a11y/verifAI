from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.ml_decision.dataset_builder import collect_final_decision_training_rows
from app.ml_decision.feature_engineering import (
    ALLOWED_FINAL_LABELS,
    FinalDecisionFeatures,
    build_feature_payload,
    normalize_final_label,
)
from app.ml_decision.model import FinalDecisionModelArtifact, predict_proba, train_random_forest


MODEL_KEY = "final_decision_rf"


def _default_model_path() -> Path:
    # Prompt expects ml/model.pkl at repo root by default.
    configured = str(getattr(settings, "ml_final_decision_model_path", "") or "").strip()
    if configured:
        return Path(configured)
    return Path("ml") / "model.pkl"


def _dump_artifact(path: Path, artifact: FinalDecisionModelArtifact) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import joblib  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("joblib is required for ML artifact I/O (install scikit-learn)") from exc

    joblib.dump(artifact, str(path))
    # Sidecar metadata for quick inspection.
    meta_path = path.with_suffix(".meta.json")
    meta = asdict(artifact)
    # classifier is not JSON-serializable
    meta["classifier"] = str(type(artifact.classifier))
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_artifact(path: Path) -> FinalDecisionModelArtifact | None:
    try:
        import joblib  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        if not path.exists() or not path.is_file():
            return None
        obj = joblib.load(str(path))
        return obj if isinstance(obj, FinalDecisionModelArtifact) else None
    except Exception:
        return None


_MODEL_CACHE: FinalDecisionModelArtifact | None = None


@dataclass
class FinalDecisionMLPrediction:
    available: bool
    label: str | None = None
    confidence: float = 0.0
    probabilities: dict[str, float] | None = None
    model_version: str | None = None
    training_examples: int = 0
    reason: str | None = None


def ensure_final_decision_model(db: Session, *, force_retrain: bool = False) -> FinalDecisionModelArtifact | None:
    global _MODEL_CACHE

    if force_retrain:
        artifact = train_final_decision_model(db=db, force_retrain=True)
        _MODEL_CACHE = artifact
        return artifact

    if _MODEL_CACHE is not None:
        return _MODEL_CACHE

    artifact = _load_artifact(_default_model_path())
    _MODEL_CACHE = artifact
    return artifact


def train_final_decision_model(db: Session, *, force_retrain: bool = True, limit: int = 50000) -> FinalDecisionModelArtifact | None:
    rows = collect_final_decision_training_rows(db, limit=int(limit))
    examples: list[tuple[FinalDecisionFeatures, str]] = []
    for row in rows:
        label = normalize_final_label(row.label)
        if label is None or label not in ALLOWED_FINAL_LABELS:
            continue
        examples.append((row.features, label))

    artifact = train_random_forest(examples, model_key=MODEL_KEY)
    if artifact is None:
        return None

    _dump_artifact(_default_model_path(), artifact)
    return artifact


def predict_final_decision(
    db: Session | None,
    *,
    ai_decision: Any,
    ai_confidence: Any,
    risk_score: Any,
    conflict_count: Any,
    rule_hit_count: Any,
    verifications: dict[str, Any] | None,
    amount: Any,
    diagnosis: Any,
    hospital: Any,
    min_confidence: float = 0.75,
) -> FinalDecisionMLPrediction:
    model = ensure_final_decision_model(db, force_retrain=False) if db is not None else _load_artifact(_default_model_path())
    if model is None:
        return FinalDecisionMLPrediction(available=False, reason="model not trained")

    features = build_feature_payload(
        ai_decision=ai_decision,
        ai_confidence=ai_confidence,
        risk_score=risk_score,
        conflict_count=conflict_count,
        rule_hit_count=rule_hit_count,
        verifications=verifications,
        amount=amount,
        diagnosis=diagnosis,
        hospital=hospital,
    )

    probs = predict_proba(model, features)
    if not probs:
        return FinalDecisionMLPrediction(available=False, reason="model returned empty probabilities")
    best_label = max(probs.items(), key=lambda kv: kv[1])[0]
    best_conf = float(probs.get(best_label) or 0.0)
    used = best_conf >= float(min_confidence or 0.0)
    return FinalDecisionMLPrediction(
        available=True,
        label=str(best_label),
        confidence=best_conf,
        probabilities=probs,
        model_version=str(model.version),
        training_examples=int(model.num_examples),
        reason=("ok" if used else f"below threshold {min_confidence}"),
    )

