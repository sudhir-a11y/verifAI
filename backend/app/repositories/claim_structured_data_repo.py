"""Repository for claim_structured_data table.

DDL + basic CRUD — no business logic.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def ensure_table(db: Session) -> None:
    """Ensure the claim_structured_data table exists."""
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS claim_structured_data (
                id BIGSERIAL PRIMARY KEY,
                claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
                structured_json JSONB NOT NULL,
                provider TEXT NOT NULL DEFAULT 'llm',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        ),
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_claim_structured_data_claim_id ON claim_structured_data(claim_id)"
        ),
    )


def upsert_structured_data(
    db: Session,
    *,
    claim_id: str,
    structured_json: dict[str, Any],
    provider: str = "llm",
) -> None:
    """Insert or update structured data for a claim."""
    import json

    db.execute(
        text(
            """
            INSERT INTO claim_structured_data (claim_id, structured_json, provider)
            VALUES (:claim_id, CAST(:structured_json AS jsonb), :provider)
            ON CONFLICT (claim_id) DO UPDATE
            SET structured_json = EXCLUDED.structured_json,
                provider = EXCLUDED.provider,
                updated_at = NOW()
            """
        ),
        {
            "claim_id": claim_id,
            "structured_json": json.dumps(structured_json),
            "provider": provider,
        },
    )


def get_structured_data(db: Session, claim_id: str) -> dict[str, Any] | None:
    """Get the latest structured data for a claim."""
    row = db.execute(
        text(
            """
            SELECT structured_json, provider, created_at, updated_at
            FROM claim_structured_data
            WHERE claim_id = :claim_id
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ),
        {"claim_id": claim_id},
    ).mappings().first()
    return dict(row) if row else None
