from __future__ import annotations

import json
import sys
from pathlib import Path


def _bootstrap_backend_imports() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    backend_dir = repo_root / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))


def demo() -> None:
    _bootstrap_backend_imports()

    from app.ml_decision.feature_engineering import build_feature_payload, featurize  # noqa: E402

    features = build_feature_payload(
        ai_decision="approve",
        ai_confidence=0.83,
        risk_score=0.22,
        conflict_count=0,
        rule_hit_count=2,
        verifications={"doctor_valid": True, "hospital_gst_valid": True, "pharmacy_gst_valid": None, "drug_license_valid": True},
        amount="125000",
        diagnosis="appendicitis",
        hospital="City Hospital",
    )
    vec, names = featurize(features, diagnosis_vocab=["appendicitis"], hospital_vocab=["city", "hospital"])
    print(json.dumps({"features": features.__dict__, "vector": vec, "names": names}, indent=2))


if __name__ == "__main__":
    demo()

