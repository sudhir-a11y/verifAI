from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def ensure_table(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS workflow_job_locks (
                job_key TEXT PRIMARY KEY,
                claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
                job_type TEXT NOT NULL,
                locked_by TEXT NOT NULL,
                acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ NOT NULL
            )
            """
        )
    )
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_workflow_job_locks_claim_id ON workflow_job_locks(claim_id)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_workflow_job_locks_expires_at ON workflow_job_locks(expires_at)"))


def acquire_lock(
    db: Session,
    *,
    claim_id: UUID,
    job_type: str,
    locked_by: str,
    ttl_seconds: int = 900,
) -> bool:
    ensure_table(db)
    key = f"{job_type}:{str(claim_id)}"
    ttl_seconds = max(30, int(ttl_seconds or 900))

    db.execute(text("DELETE FROM workflow_job_locks WHERE expires_at < NOW()"))

    row = db.execute(
        text(
            """
            INSERT INTO workflow_job_locks (job_key, claim_id, job_type, locked_by, acquired_at, expires_at)
            VALUES (:job_key, :claim_id, :job_type, :locked_by, NOW(), NOW() + (:ttl_seconds * INTERVAL '1 second'))
            ON CONFLICT (job_key)
            DO UPDATE SET
                claim_id = EXCLUDED.claim_id,
                job_type = EXCLUDED.job_type,
                locked_by = EXCLUDED.locked_by,
                acquired_at = NOW(),
                expires_at = NOW() + (:ttl_seconds * INTERVAL '1 second')
            WHERE workflow_job_locks.expires_at < NOW()
            RETURNING job_key
            """
        ),
        {
            "job_key": key,
            "claim_id": str(claim_id),
            "job_type": str(job_type or "unknown"),
            "locked_by": str(locked_by or "system"),
            "ttl_seconds": ttl_seconds,
        },
    ).mappings().first()
    return bool(row)


def release_lock(db: Session, *, claim_id: UUID, job_type: str, locked_by: str | None = None) -> int:
    key = f"{job_type}:{str(claim_id)}"
    params: dict[str, Any] = {"job_key": key}
    sql = "DELETE FROM workflow_job_locks WHERE job_key = :job_key"
    if str(locked_by or "").strip():
        sql += " AND locked_by = :locked_by"
        params["locked_by"] = str(locked_by)
    return int(db.execute(text(sql), params).rowcount or 0)
