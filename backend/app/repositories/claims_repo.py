import json
import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.claim import ClaimStatus, CreateClaimRequest


class DuplicateClaimIdDbError(IntegrityError):
    """Marker for unique violations when inserting claims."""


def ensure_claim_completed_at_column(db: Session) -> None:
    db.execute(text("ALTER TABLE claims ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_claims_completed_at ON claims(completed_at)"))


def ensure_claim_completed_at_column_and_backfill(db: Session) -> None:
    ensure_claim_completed_at_column(db)
    db.execute(
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
    db.execute(
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
