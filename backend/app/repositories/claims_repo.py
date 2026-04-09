import json
import re
from threading import Lock
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import engine
from app.schemas.claim import ClaimStatus, CreateClaimRequest


class DuplicateClaimIdDbError(IntegrityError):
    """Marker for unique violations when inserting claims."""

_COMPLETED_AT_BOOTSTRAPPED = False
_COMPLETED_AT_BOOTSTRAP_LOCK = Lock()


def ensure_claim_completed_at_column(db: Session) -> None:
    """
    Ensure `claims.completed_at` exists.

    IMPORTANT: Don't run DDL on request sessions (it can take an
    ACCESS EXCLUSIVE lock and block concurrent reads/writes). We run it once per
    process using a dedicated connection that commits immediately.
    """
    global _COMPLETED_AT_BOOTSTRAPPED
    if _COMPLETED_AT_BOOTSTRAPPED:
        return
    with _COMPLETED_AT_BOOTSTRAP_LOCK:
        if _COMPLETED_AT_BOOTSTRAPPED:
            return

        # Fast-path: if both column + index already exist, avoid taking DDL locks.
        # (Even IF NOT EXISTS statements still need table-level locks.)
        try:
            with engine.connect() as conn:
                has_column = bool(
                    conn.execute(
                        text(
                            """
                            SELECT 1
                            FROM pg_attribute
                            WHERE attrelid = 'claims'::regclass
                              AND attname = 'completed_at'
                              AND NOT attisdropped
                            LIMIT 1
                            """
                        )
                    ).scalar()
                )
                has_index = bool(
                    conn.execute(text("SELECT to_regclass('idx_claims_completed_at')")).scalar()
                )
        except Exception:
            # If introspection fails, fall back to the safest behavior: attempt DDL,
            # but with short lock timeouts so we don't hang request threads.
            has_column = False
            has_index = False

        if not has_column:
            with engine.begin() as conn:
                conn.execute(text("SET lock_timeout TO '2s'"))
                conn.execute(text("SET statement_timeout TO '10s'"))
                conn.execute(
                    text(
                        "ALTER TABLE claims ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ"
                    )
                )

        if not has_index:
            # Use CONCURRENTLY to avoid blocking reads/writes on large tables.
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.execute(text("SET lock_timeout TO '2s'"))
                conn.execute(text("SET statement_timeout TO '30s'"))
                conn.execute(
                    text(
                        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_claims_completed_at ON claims(completed_at)"
                    )
                )

        _COMPLETED_AT_BOOTSTRAPPED = True


def ensure_claim_completed_at_column_and_backfill(db: Session) -> None:
    ensure_claim_completed_at_column(db)
    # Backfill can be expensive; run it once per process and commit immediately
    # to avoid holding locks in read-only API requests.
    # (Used by Payment Sheet + other reporting endpoints.)
    global _COMPLETED_AT_BACKFILLED
    if _COMPLETED_AT_BACKFILLED:
        return
    with _COMPLETED_AT_BACKFILL_LOCK:
        if _COMPLETED_AT_BACKFILLED:
            return
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    WITH first_completed AS (
                        SELECT
                            we.claim_id,
                            MIN(we.occurred_at) AS first_completed_at
                        FROM workflow_events we
                        WHERE we.event_type = 'claim_status_updated'
                          AND COALESCE(we.event_payload->>'status', '') = 'completed'
                        GROUP BY we.claim_id
                    )
                    UPDATE claims c
                    SET completed_at = fc.first_completed_at
                    FROM first_completed fc
                    WHERE c.id = fc.claim_id
                      AND c.status = 'completed'
                      AND c.completed_at IS NULL
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE claims
                    SET completed_at = updated_at
                    WHERE status = 'completed'
                      AND completed_at IS NULL
                      AND updated_at IS NOT NULL
                    """
                )
            )
        _COMPLETED_AT_BACKFILLED = True


_COMPLETED_AT_BACKFILLED = False
_COMPLETED_AT_BACKFILL_LOCK = Lock()


def insert_claim(db: Session, payload: CreateClaimRequest) -> dict[str, Any]:
    ensure_claim_completed_at_column(db)
    try:
        result = db.execute(
            text(
                """
                INSERT INTO claims (
                    external_claim_id,
                    patient_name,
                    patient_identifier,
                    status,
                    assigned_doctor_id,
                    priority,
                    source_channel,
                    tags,
                    completed_at
                )
                VALUES (
                    :external_claim_id,
                    :patient_name,
                    :patient_identifier,
                    :status,
                    :assigned_doctor_id,
                    :priority,
                    :source_channel,
                    CAST(:tags AS jsonb),
                    CASE WHEN CAST(:status AS claim_status) = 'completed'::claim_status THEN NOW() ELSE NULL END
                )
                RETURNING
                    id,
                    external_claim_id,
                    patient_name,
                    patient_identifier,
                    status,
                    assigned_doctor_id,
                    priority,
                    source_channel,
                    tags,
                    created_at,
                    updated_at
                """
            ),
            {
                "external_claim_id": payload.external_claim_id,
                "patient_name": payload.patient_name,
                "patient_identifier": payload.patient_identifier,
                "status": payload.status.value,
                "assigned_doctor_id": payload.assigned_doctor_id,
                "priority": payload.priority,
                "source_channel": payload.source_channel,
                "tags": json.dumps(payload.tags),
            },
        ).mappings().one()
        return dict(result)
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise DuplicateClaimIdDbError(str(exc)) from exc
        raise


def get_claim_by_id(db: Session, claim_id: UUID) -> dict[str, Any] | None:
    ensure_claim_completed_at_column(db)
    row = db.execute(
        text(
            """
            SELECT
                id,
                external_claim_id,
                patient_name,
                patient_identifier,
                status,
                assigned_doctor_id,
                priority,
                source_channel,
                tags,
                created_at,
                updated_at
            FROM claims
            WHERE id = :claim_id
            """
        ),
        {"claim_id": str(claim_id)},
    ).mappings().first()
    return dict(row) if row is not None else None


def get_claim_assigned_doctor_id(db: Session, *, claim_id: UUID) -> str | None:
    row = db.execute(
        text("SELECT assigned_doctor_id FROM claims WHERE id = :claim_id"),
        {"claim_id": str(claim_id)},
    ).mappings().first()
    if row is None:
        return None
    return str(row.get("assigned_doctor_id") or "")


def get_completed_claim_external_id(db: Session, *, claim_id: UUID) -> str | None:
    row = db.execute(
        text(
            """
            SELECT external_claim_id
            FROM claims
            WHERE id = :claim_id
              AND status = 'completed'
            LIMIT 1
            """
        ),
        {"claim_id": str(claim_id)},
    ).mappings().first()
    if row is None:
        return None
    value = str(row.get("external_claim_id") or "").strip()
    return value or None


def get_claim_id_by_external_id_and_source(
    db: Session, *, external_claim_id: str, source_channel: str
) -> str | None:
    row = db.execute(
        text(
            """
            SELECT id
            FROM claims
            WHERE external_claim_id = :external_claim_id
              AND COALESCE(source_channel, '') = :source_channel
            LIMIT 1
            """
        ),
        {"external_claim_id": external_claim_id, "source_channel": source_channel},
    ).mappings().first()
    if row is None:
        return None
    return str(row.get("id") or "") or None


def get_claim_row_by_external_claim_id(db: Session, *, external_claim_id: str) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT id, external_claim_id
            FROM claims
            WHERE external_claim_id = :external_claim_id
            LIMIT 1
            """
        ),
        {"external_claim_id": str(external_claim_id)},
    ).mappings().first()
    return dict(row) if row is not None else None


def insert_claim_from_integration(
    db: Session,
    *,
    external_claim_id: str,
    patient_name: str | None,
    patient_identifier: str | None,
    status: str,
    assigned_doctor_id: str | None,
    priority: int,
    source_channel: str,
    tags: list[str],
) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            INSERT INTO claims (
                external_claim_id,
                patient_name,
                patient_identifier,
                status,
                assigned_doctor_id,
                priority,
                source_channel,
                tags,
                completed_at
            )
            VALUES (
                :external_claim_id,
                :patient_name,
                :patient_identifier,
                CAST(:status AS claim_status),
                :assigned_doctor_id,
                :priority,
                :source_channel,
                CAST(:tags AS jsonb),
                CASE WHEN CAST(:status AS claim_status) = 'completed'::claim_status THEN NOW() ELSE NULL END
            )
            RETURNING id, external_claim_id
            """
        ),
        {
            "external_claim_id": str(external_claim_id),
            "patient_name": patient_name,
            "patient_identifier": patient_identifier,
            "status": str(status),
            "assigned_doctor_id": assigned_doctor_id,
            "priority": int(priority),
            "source_channel": str(source_channel or ""),
            "tags": json.dumps(tags or []),
        },
    ).mappings().one()
    return dict(row)


def update_claim_from_integration(
    db: Session,
    *,
    claim_id: str,
    patient_name: str,
    patient_identifier: str,
    assigned_doctor_id: str,
    status: str,
    priority: int,
    source_channel: str,
    tags: list[str] | None,
) -> None:
    db.execute(
        text(
            """
            UPDATE claims
            SET
                patient_name = COALESCE(NULLIF(:patient_name, ''), patient_name),
                patient_identifier = COALESCE(NULLIF(:patient_identifier, ''), patient_identifier),
                assigned_doctor_id = COALESCE(NULLIF(:assigned_doctor_id, ''), assigned_doctor_id),
                status = COALESCE(CAST(:status AS claim_status), status),
                completed_at = CASE WHEN CAST(:status AS claim_status) = 'completed'::claim_status THEN COALESCE(completed_at, NOW()) ELSE completed_at END,
                priority = COALESCE(:priority, priority),
                source_channel = COALESCE(NULLIF(:source_channel, ''), source_channel),
                tags = COALESCE(CAST(:tags_json AS jsonb), tags),
                updated_at = NOW()
            WHERE id = :claim_id
            """
        ),
        {
            "claim_id": str(claim_id),
            "patient_name": str(patient_name or ""),
            "patient_identifier": str(patient_identifier or ""),
            "assigned_doctor_id": str(assigned_doctor_id or ""),
            "status": str(status),
            "priority": int(priority),
            "source_channel": str(source_channel or ""),
            "tags_json": json.dumps(tags) if tags is not None else None,
        },
    )


def _normalize_doctor_token(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _split_doctor_list(raw: str | None) -> list[str]:
    values: list[str] = []
    for part in str(raw or "").split(","):
        token = _normalize_doctor_token(part)
        if token:
            values.append(token)
    return values


def _build_doctor_membership_clauses(doctor_values: list[str], params: dict[str, Any]) -> list[str]:
    clauses: list[str] = []
    for idx, doctor in enumerate(doctor_values):
        key = f"doctor_{idx}"
        params[key] = _normalize_doctor_token(doctor)
        clauses.append(
            f":{key} = ANY(string_to_array(regexp_replace(lower(COALESCE(assigned_doctor_id, '')), '[^a-z0-9,]+', '', 'g'), ','))"
        )
    return clauses


def list_claim_rows(
    db: Session,
    status: ClaimStatus | None,
    assigned_doctor_id: str | None,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, Any]]]:
    ensure_claim_completed_at_column(db)
    filters: list[str] = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if status is not None:
        filters.append("status = :status")
        params["status"] = status.value

    if assigned_doctor_id:
        doctor_values = _split_doctor_list(assigned_doctor_id)
        if doctor_values:
            doctor_clauses = _build_doctor_membership_clauses(doctor_values, params)
            filters.append("(" + " OR ".join(doctor_clauses) + ")")

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    total = db.execute(
        text(f"SELECT COUNT(*) AS total FROM claims {where_clause}"),
        params,
    ).scalar_one()

    rows = db.execute(
        text(
            f"""
            SELECT
                id,
                external_claim_id,
                patient_name,
                patient_identifier,
                status,
                assigned_doctor_id,
                priority,
                source_channel,
                tags,
                created_at,
                updated_at
            FROM claims
            {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()

    return int(total or 0), [dict(r) for r in rows]


def update_claim_status_row(db: Session, claim_id: UUID, status: ClaimStatus) -> dict[str, Any] | None:
    ensure_claim_completed_at_column(db)
    row = db.execute(
        text(
            """
            UPDATE claims
            SET status = CAST(:status AS claim_status),
                completed_at = CASE WHEN CAST(:status AS claim_status) = 'completed'::claim_status THEN COALESCE(completed_at, NOW()) ELSE completed_at END
            WHERE id = :claim_id
            RETURNING
                id,
                external_claim_id,
                patient_name,
                patient_identifier,
                status,
                assigned_doctor_id,
                priority,
                source_channel,
                tags,
                created_at,
                updated_at
            """
        ),
        {"status": status.value, "claim_id": str(claim_id)},
    ).mappings().first()
    return dict(row) if row is not None else None


def assign_claim_row(
    db: Session,
    claim_id: UUID,
    assigned_doctor_id: str,
    *,
    status: ClaimStatus | None = None,
) -> dict[str, Any] | None:
    ensure_claim_completed_at_column(db)
    if status is None:
        sql_stmt = text(
            """
            UPDATE claims
            SET assigned_doctor_id = :assigned_doctor_id
            WHERE id = :claim_id
            RETURNING
                id,
                external_claim_id,
                patient_name,
                patient_identifier,
                status,
                assigned_doctor_id,
                priority,
                source_channel,
                tags,
                created_at,
                updated_at
            """
        )
        params = {"assigned_doctor_id": assigned_doctor_id, "claim_id": str(claim_id)}
    else:
        sql_stmt = text(
            """
            UPDATE claims
            SET assigned_doctor_id = :assigned_doctor_id,
                status = CAST(:status AS claim_status),
                completed_at = CASE WHEN CAST(:status AS claim_status) = 'completed'::claim_status THEN COALESCE(completed_at, NOW()) ELSE completed_at END
            WHERE id = :claim_id
            RETURNING
                id,
                external_claim_id,
                patient_name,
                patient_identifier,
                status,
                assigned_doctor_id,
                priority,
                source_channel,
                tags,
                created_at,
                updated_at
            """
        )
        params = {"assigned_doctor_id": assigned_doctor_id, "status": status.value, "claim_id": str(claim_id)}

    row = db.execute(sql_stmt, params).mappings().first()
    return dict(row) if row is not None else None


def claim_exists(db: Session, claim_id: UUID) -> bool:
    """Check if a claim exists by id."""
    row = db.execute(
        text("SELECT 1 FROM claims WHERE id = :claim_id LIMIT 1"),
        {"claim_id": str(claim_id)},
    ).first()
    return row is not None


def get_claim_by_external_id(db: Session, external_claim_id: str, source_channel: str) -> dict[str, Any] | None:
    """Get a claim by external ID and source channel."""
    row = db.execute(
        text(
            """
            SELECT * FROM claims
            WHERE external_claim_id = :external_claim_id
              AND COALESCE(source_channel, '') = :source_channel
            LIMIT 1
            """
        ),
        {"external_claim_id": external_claim_id, "source_channel": source_channel},
    ).mappings().first()
    return dict(row) if row else None


def bulk_upsert_claims(db: Session, claims: list[dict[str, Any]]) -> int:
    """Bulk upsert claims. Returns the number of rows affected."""
    if not claims:
        return 0
    result = db.execute(
        text(
            """
            INSERT INTO claims (
                external_claim_id, patient_name, patient_identifier,
                status, assigned_doctor_id, priority, source_channel, tags
            ) VALUES (
                :external_claim_id, :patient_name, :patient_identifier,
                :status, :assigned_doctor_id, :priority, :source_channel,
                CAST(:tags AS jsonb)
            )
            ON CONFLICT (external_claim_id, source_channel) DO UPDATE
            SET patient_name = EXCLUDED.patient_name,
                patient_identifier = EXCLUDED.patient_identifier,
                status = EXCLUDED.status,
                assigned_doctor_id = EXCLUDED.assigned_doctor_id,
                priority = EXCLUDED.priority,
                tags = EXCLUDED.tags,
                updated_at = NOW()
            """
        ),
        claims,
    )
    return int(result.rowcount or 0)


def get_assigned_doctor_ids_for_teamrightworks(db: Session) -> list[str]:
    """Get all assigned doctor IDs for teamrightworks claims."""
    rows = db.execute(
        text(
            """
            SELECT assigned_doctor_id
            FROM claims
            WHERE COALESCE(source_channel, '') = 'teamrightworks.in'
              AND COALESCE(assigned_doctor_id, '') <> ''
            """
        ),
    ).mappings().all()
    return [str(r.get("assigned_doctor_id") or "") for r in rows if r.get("assigned_doctor_id")]
