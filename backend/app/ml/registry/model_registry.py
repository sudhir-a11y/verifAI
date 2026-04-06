"""Model registry — versioning, artifact storage.

Delegates SQL to repositories.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.repositories import model_registry_repo

MODEL_KEY = "claim_recommendation_nb"
MODEL_VERSION_PREFIX = "nb-v2"
ARTIFACT_DIR = Path("artifacts") / "ml"


def write_artifact(model: dict[str, Any], version: str) -> str:
    """Write model artifact as JSON file. Returns the artifact path."""
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = ARTIFACT_DIR / f"{MODEL_KEY}_{version}.json"
    artifact_path.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
    return str(artifact_path)


def read_artifact(path_value: str) -> dict[str, Any] | None:
    """Read a model artifact from a JSON file path."""
    try:
        path = Path(path_value)
        if not path.exists() or not path.is_file():
            return None
        body = json.loads(path.read_text(encoding="utf-8"))
        return body if isinstance(body, dict) else None
    except Exception:
        return None


def persist_registry(db: Session, version: str, artifact_uri: str, model: dict[str, Any]) -> None:
    """Register a model version in the model_registry table."""
    metrics = {
        "algorithm": model.get("algorithm"),
        "num_examples": model.get("num_examples"),
        "label_counts": model.get("label_counts"),
        "vocab_size": len(model.get("vocab") or []),
        "trained_at": model.get("trained_at"),
    }
    model_registry_repo.persist_model_version(db, version=version, metrics=metrics, artifact_uri=artifact_uri)


def load_latest_from_registry(db: Session) -> dict[str, Any] | None:
    """Load the latest active model from the registry."""
    row = model_registry_repo.load_latest_model_version(db)
    if row is None:
        return None

    artifact_uri = str(row.get("artifact_uri") or "").strip()
    model = read_artifact(artifact_uri) if artifact_uri else None
    if not isinstance(model, dict):
        return None

    model["version"] = str(row.get("version") or model.get("version") or "")
    return model
