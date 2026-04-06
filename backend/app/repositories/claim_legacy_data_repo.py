"""Repository for claim_legacy_data table."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def ensure_table(db: Session) -> None:
    """Ensure the claim_legacy_data table exists."""
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS claim_legacy_data (
                id BIGSERIAL PRIMARY KEY,
                claim_id UUID NOT NULL UNIQUE REFERENCES claims(id) ON DELETE CASCADE,
                legacy_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_claim_legacy_data_claim_id ON claim_legacy_data(claim_id)"))


def ensure_claim_legacy_data_table(db: Session) -> None:
    """Backward-compatible alias."""
    ensure_table(db)


def get_by_claim_id(db: Session, claim_id: str) -> dict[str, Any] | None:
    """Get legacy data for a claim."""
    row = db.execute(
        text(
            "SELECT * FROM claim_legacy_data WHERE claim_id = :claim_id LIMIT 1"
        ),
        {"claim_id": claim_id},
    ).mappings().first()
    return dict(row) if row else None


def upsert_legacy_data(db: Session, claim_id: str, legacy_payload: dict[str, Any]) -> None:
    """Insert or update legacy data for a claim."""
    import json

    db.execute(
        text(
            """
            INSERT INTO claim_legacy_data (claim_id, legacy_payload)
            VALUES (:claim_id, CAST(:legacy_payload AS jsonb))
            ON CONFLICT (claim_id) DO UPDATE
            SET legacy_payload = EXCLUDED.legacy_payload,
                updated_at = NOW()
            """
        ),
        {
            "claim_id": claim_id,
            "legacy_payload": json.dumps(legacy_payload),
        },
    )
