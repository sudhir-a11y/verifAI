from sqlalchemy import text
from sqlalchemy.orm import Session


def ensure_claim_legacy_data_table(db: Session) -> None:
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

