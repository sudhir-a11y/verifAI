"""Repository for claim_provider_registry_clean table.

Provider tracking — no business logic.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def ensure_table(db: Session) -> None:
    """Ensure the claim_provider_registry_clean table exists."""
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS claim_provider_registry_clean (
                id BIGSERIAL PRIMARY KEY,
                claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        ),
    )
    db.execute(
        text("CREATE INDEX IF NOT EXISTS idx_provider_registry_clean_hospital ON claim_provider_registry_clean(hospital_norm)")
    )
    db.execute(
        text("CREATE INDEX IF NOT EXISTS idx_provider_registry_clean_doctor ON claim_provider_registry_clean(doctor_norm)")
    )
    db.execute(
        text("CREATE INDEX IF NOT EXISTS idx_provider_registry_clean_reg ON claim_provider_registry_clean(reg_norm)")
    )


def delete_by_claim_id(db: Session, claim_id: str) -> None:
    """Delete provider registry entries for a claim."""
    db.execute(
        text(
            "DELETE FROM claim_provider_registry_clean WHERE claim_id = :claim_id"
        ),
        {"claim_id": claim_id},
    )


def insert_provider_entry(
    db: Session,
    *,
    claim_id: str,
    provider: str,
    status: str = "pending",
) -> None:
    """Insert a provider registry entry."""
    db.execute(
        text(
            """
            INSERT INTO claim_provider_registry_clean (claim_id, provider, status)
            VALUES (:claim_id, :provider, :status)
            """
        ),
        {
            "claim_id": claim_id,
            "provider": provider,
            "status": status,
        },
    )
