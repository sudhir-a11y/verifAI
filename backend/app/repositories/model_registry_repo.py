from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_latest_trained_at(db: Session, *, model_key: str) -> Any | None:
    row = db.execute(
        text(
            """
            SELECT COALESCE(effective_from, created_at) AS trained_at
            FROM model_registry
            WHERE model_key = :model_key
            ORDER BY
                CASE WHEN status = 'active' THEN 0 ELSE 1 END,
                COALESCE(effective_from, created_at) DESC,
                created_at DESC
            LIMIT 1
            """
        ),
        {"model_key": model_key},
    ).mappings().first()
    if row is None:
        return None
    return row.get("trained_at")


def persist_model_version(
    db: Session,
    *,
    version: str,
    metrics: dict[str, Any],
    artifact_uri: str,
    model_key: str = "claim_recommendation_nb",
    status: str = "active",
) -> None:
    """Insert or update a model version in the model_registry table."""
    db.execute(
        text(
            """
            INSERT INTO model_registry (
                model_key, version, status, metrics, artifact_uri,
                approved_by, approved_at, effective_from
            ) VALUES (
                :model_key, :version, :status, CAST(:metrics AS jsonb), :artifact_uri,
                'system', NOW(), NOW()
            )
            ON CONFLICT (model_key, version) DO UPDATE SET
                status = EXCLUDED.status,
                metrics = EXCLUDED.metrics,
                artifact_uri = EXCLUDED.artifact_uri,
                effective_from = EXCLUDED.effective_from
            """
        ),
        {
            "model_key": model_key,
            "version": version,
            "status": status,
            "metrics": json.dumps(metrics, ensure_ascii=False),
            "artifact_uri": artifact_uri,
        },
    )


def load_latest_model_version(db: Session, *, model_key: str = "claim_recommendation_nb") -> dict[str, Any] | None:
    """Load the latest active model version from the registry."""
    row = db.execute(
        text(
            """
            SELECT
                version, status, metrics, artifact_uri,
                COALESCE(effective_from, created_at) AS effective_from
            FROM model_registry
            WHERE model_key = :model_key
              AND status = 'active'
            ORDER BY COALESCE(effective_from, created_at) DESC
            LIMIT 1
            """
        ),
        {"model_key": model_key},
    ).mappings().first()

    if row is None:
        return None

    result = dict(row)
    metrics = row.get("metrics")
    if isinstance(metrics, dict):
        result["metrics"] = metrics
    elif isinstance(metrics, str):
        try:
            result["metrics"] = json.loads(metrics)
        except json.JSONDecodeError:
            result["metrics"] = {}
    else:
        result["metrics"] = {}

    return result

