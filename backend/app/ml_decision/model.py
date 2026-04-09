from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.ml_decision.feature_engineering import (
    ALLOWED_FINAL_LABELS,
    FinalDecisionFeatures,
    build_vocabs,
    featurize,
)


@dataclass
class FinalDecisionModelArtifact:
    model_key: str
    version: str
    trained_at: str
    algorithm: str
    label_order: list[str]
    feature_names: list[str]
    diagnosis_vocab: list[str]
    hospital_vocab: list[str]
    classifier: Any
    num_examples: int
    label_counts: dict[str, int]


def _require_sklearn() -> tuple[Any, Any]:
    try:
        from sklearn.ensemble import RandomForestClassifier  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("scikit-learn is required for FinalDecision ML. Install: pip install scikit-learn") from exc
    try:
        import numpy as np  # numpy is already a dependency
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("numpy is required for FinalDecision ML") from exc
    return RandomForestClassifier, np


def train_random_forest(
    examples: list[tuple[FinalDecisionFeatures, str]],
    *,
    model_key: str,
    diagnosis_vocab_size: int = 60,
    hospital_vocab_size: int = 60,
    n_estimators: int = 220,
    random_state: int = 42,
) -> FinalDecisionModelArtifact | None:
    if len(examples) < 30:
        return None

    RandomForestClassifier, np = _require_sklearn()

    labels = [label for _, label in examples]
    label_counts: dict[str, int] = {}
    for label in labels:
        label_counts[label] = int(label_counts.get(label, 0) + 1)
    # Need at least 2 classes to train.
    if len(label_counts) < 2:
        return None

    rows = [feat for feat, _ in examples]
    diag_vocab, hosp_vocab = build_vocabs(
        rows,
        diagnosis_max_tokens=int(diagnosis_vocab_size),
        hospital_max_tokens=int(hospital_vocab_size),
    )

    X_list: list[list[float]] = []
    feature_names: list[str] = []
    for feat, _label in examples:
        vec, names = featurize(feat, diagnosis_vocab=diag_vocab, hospital_vocab=hosp_vocab)
        if not feature_names:
            feature_names = names
        X_list.append(vec)

    X = np.asarray(X_list, dtype=float)
    y = np.asarray(labels, dtype=object)

    clf = RandomForestClassifier(
        n_estimators=int(n_estimators),
        random_state=int(random_state),
        class_weight="balanced",
        max_depth=12,
        min_samples_leaf=2,
        n_jobs=-1,
    )
    clf.fit(X, y)

    trained_at = datetime.now(timezone.utc).isoformat()
    version = datetime.now(timezone.utc).strftime("rf-v1-%Y%m%d%H%M%S")

    # Stable label order used for proba output.
    label_order = [c for c in getattr(clf, "classes_", [])]
    label_order = [str(x) for x in label_order if str(x) in ALLOWED_FINAL_LABELS]
    if not label_order:
        # Fallback to observed.
        label_order = sorted(set(labels))

    return FinalDecisionModelArtifact(
        model_key=str(model_key),
        version=version,
        trained_at=trained_at,
        algorithm="random_forest_classifier",
        label_order=label_order,
        feature_names=feature_names,
        diagnosis_vocab=diag_vocab,
        hospital_vocab=hosp_vocab,
        classifier=clf,
        num_examples=int(len(examples)),
        label_counts=label_counts,
    )


def predict_proba(
    artifact: FinalDecisionModelArtifact,
    features: FinalDecisionFeatures,
) -> dict[str, float]:
    _, np = _require_sklearn()
    vec, _names = featurize(features, diagnosis_vocab=artifact.diagnosis_vocab, hospital_vocab=artifact.hospital_vocab)
    X = np.asarray([vec], dtype=float)
    clf = artifact.classifier
    proba = clf.predict_proba(X)[0]
    classes = [str(c) for c in getattr(clf, "classes_", [])]
    probs: dict[str, float] = {}
    for idx, cls in enumerate(classes):
        if cls in ALLOWED_FINAL_LABELS:
            probs[cls] = float(proba[idx])
    # Normalize in case of unexpected classes.
    s = sum(probs.values()) or 1.0
    for k in list(probs.keys()):
        probs[k] = probs[k] / s
    return probs

