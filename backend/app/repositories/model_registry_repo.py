from __future__ import annotations

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

