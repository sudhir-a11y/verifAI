from __future__ import annotations

import math
from typing import Any


def _clamp01(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return float(default)
    if math.isnan(x) or math.isinf(x):
        return float(default)
    return max(0.0, min(1.0, x))


def compute_verification_confidence(verifications: dict[str, Any]) -> float:
    if not isinstance(verifications, dict) or not verifications:
        return 0.6
    score = 1.0
    for _key, val in verifications.items():
        if val is False:
            score -= 0.35
        elif val is None:
            score -= 0.08
    return max(0.05, min(1.0, score))


def aggregate_confidence(
    *,
    ai_confidence: float | None,
    verification_confidence: float | None,
    human_confidence: float | None,
    has_doctor: bool,
    has_auditor: bool,
) -> tuple[float, dict[str, Any]]:
    ai_c = _clamp01(ai_confidence, default=0.5)
    ver_c = _clamp01(verification_confidence, default=0.6)
    human_c = _clamp01(human_confidence, default=0.0)

    if has_auditor:
        weights = {"ai": 0.15, "verification": 0.15, "human": 0.7}
    elif has_doctor:
        weights = {"ai": 0.25, "verification": 0.15, "human": 0.6}
    else:
        weights = {"ai": 0.65, "verification": 0.35, "human": 0.0}

    combined = ai_c * weights["ai"] + ver_c * weights["verification"] + human_c * weights["human"]
    return _clamp01(combined, default=0.0), {
        "weights": weights,
        "inputs": {"ai": ai_c, "verification": ver_c, "human": human_c},
    }


__all__ = ["aggregate_confidence", "compute_verification_confidence"]

