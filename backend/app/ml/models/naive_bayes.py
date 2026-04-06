"""Multinomial Naive Bayes — pure math, no DB access."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

MODEL_KEY = "claim_recommendation_nb"
MIN_TOKEN_LEN = 3
MIN_TRAINING_ROWS = 12
MAX_VOCAB = 5000


@dataclass
class MLPrediction:
    available: bool
    label: str | None = None
    confidence: float = 0.0
    probabilities: dict[str, float] | None = None
    top_signals: list[str] | None = None
    model_version: str | None = None
    training_examples: int = 0
    reason: str | None = None


# ---------------------------------------------------------------------------
# Tokenization (pure)
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    import re
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(text or "").lower())).strip()


def tokenize(text: str) -> list[str]:
    return [tok for tok in _normalize_text(text).split(" ") if len(tok) >= MIN_TOKEN_LEN]


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_naive_bayes(examples: list[tuple[str, str]]) -> dict[str, Any] | None:
    """Train a multinomial NB model from (text, label) pairs.

    Returns a model dict or None if there isn't enough data.
    """
    if len(examples) < MIN_TRAINING_ROWS:
        return None

    class_doc_counts: Counter[str] = Counter()
    token_counts_by_class: dict[str, Counter[str]] = {}
    total_token_counts: Counter[str] = Counter()

    for text_value, label in examples:
        class_doc_counts[label] += 1
        toks = tokenize(text_value)
        if label not in token_counts_by_class:
            token_counts_by_class[label] = Counter()
        token_counts_by_class[label].update(toks)
        total_token_counts.update(toks)

    if len(class_doc_counts) < 2:
        return None

    vocab = [tok for tok, _ in total_token_counts.most_common(MAX_VOCAB)]
    vocab_set = set(vocab)

    compact_counts: dict[str, dict[str, int]] = {}
    total_tokens_by_class: dict[str, int] = {}
    for label, counter in token_counts_by_class.items():
        filtered = {tok: int(cnt) for tok, cnt in counter.items() if tok in vocab_set}
        compact_counts[label] = filtered
        total_tokens_by_class[label] = int(sum(filtered.values()))

    return {
        "model_key": MODEL_KEY,
        "algorithm": "multinomial_naive_bayes",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "class_doc_counts": dict(class_doc_counts),
        "token_counts_by_class": compact_counts,
        "total_tokens_by_class": total_tokens_by_class,
        "vocab": vocab,
        "num_examples": len(examples),
        "label_counts": dict(class_doc_counts),
    }


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------

def predict(model: dict[str, Any], text_value: str) -> MLPrediction:
    """Run inference on a single text using a trained NB model."""
    vocab = model.get("vocab") or []
    if not vocab:
        return MLPrediction(available=False, reason="empty vocabulary")
    vocab_set = set(vocab)

    class_doc_counts: dict[str, int] = {k: int(v) for k, v in (model.get("class_doc_counts") or {}).items()}
    token_counts_by_class: dict[str, dict[str, int]] = {
        k: {tk: int(tv) for tk, tv in (v or {}).items()}
        for k, v in (model.get("token_counts_by_class") or {}).items()
    }
    total_tokens_by_class: dict[str, int] = {
        k: int(v) for k, v in (model.get("total_tokens_by_class") or {}).items()
    }

    if len(class_doc_counts) < 2:
        return MLPrediction(available=False, reason="not enough classes")

    token_freq = Counter([tok for tok in tokenize(text_value) if tok in vocab_set])
    classes = list(class_doc_counts.keys())
    doc_total = sum(class_doc_counts.values())
    class_count = len(classes)
    vocab_size = len(vocab)

    log_scores: dict[str, float] = {}
    for label in classes:
        prior = (class_doc_counts[label] + 1.0) / (doc_total + class_count)
        score = math.log(prior)
        class_counts = token_counts_by_class.get(label, {})
        denom = float(total_tokens_by_class.get(label, 0) + vocab_size)
        for tok, cnt in token_freq.items():
            tok_count = float(class_counts.get(tok, 0) + 1)
            score += float(cnt) * math.log(tok_count / denom)
        log_scores[label] = score

    max_log = max(log_scores.values())
    exp_scores = {k: math.exp(v - max_log) for k, v in log_scores.items()}
    prob_sum = sum(exp_scores.values()) or 1.0
    probs = {k: (v / prob_sum) for k, v in exp_scores.items()}

    sorted_probs = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
    best_label, best_conf = sorted_probs[0]
    second_label = sorted_probs[1][0] if len(sorted_probs) > 1 else best_label

    second_counts = token_counts_by_class.get(second_label, {})
    best_counts = token_counts_by_class.get(best_label, {})
    best_denom = float(total_tokens_by_class.get(best_label, 0) + vocab_size)
    second_denom = float(total_tokens_by_class.get(second_label, 0) + vocab_size)
    token_signals: list[tuple[float, str]] = []
    for tok, cnt in token_freq.items():
        p_best = (best_counts.get(tok, 0) + 1.0) / best_denom
        p_second = (second_counts.get(tok, 0) + 1.0) / second_denom
        delta = float(cnt) * (math.log(p_best) - math.log(p_second))
        token_signals.append((delta, tok))
    token_signals.sort(reverse=True)
    top_signals = [tok for delta, tok in token_signals[:8] if delta > 0]

    return MLPrediction(
        available=True,
        label=best_label,
        confidence=float(best_conf),
        probabilities=probs,
        top_signals=top_signals,
        model_version=str(model.get("version") or ""),
        training_examples=int(model.get("num_examples") or 0),
    )
