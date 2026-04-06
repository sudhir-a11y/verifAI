"""Repository for medicine_component_lookup table.

CRUD only — no business logic.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def list_medicines(
    db: Session,
    *,
    limit: int = 100,
    offset: int = 0,
    search: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """List medicines with optional search. Returns (rows, total_count)."""
    where = "WHERE medicine_name ILIKE :q OR medicine_key ILIKE :q" if search else ""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if search:
        params["q"] = f"%{search.strip()}%"

    count_row = db.execute(text(f"SELECT COUNT(*) FROM medicine_component_lookup {where}"), params).first()
    total = int(count_row[0]) if count_row else 0

    rows = db.execute(
        text(
            f"""
            SELECT id, medicine_key, medicine_name, components, subclassification,
                   is_high_end_antibiotic, source, updated_at
            FROM medicine_component_lookup
            {where}
            ORDER BY medicine_name ASC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()

    return [dict(r) for r in rows], total


def get_medicine_by_id(db: Session, medicine_id: int) -> dict[str, Any] | None:
    """Get a single medicine by id."""
    row = db.execute(
        text("SELECT * FROM medicine_component_lookup WHERE id = :id LIMIT 1"),
        {"id": medicine_id},
    ).mappings().first()
    return dict(row) if row else None


def insert_medicine(db: Session, params: dict[str, Any]) -> int:
    """Insert a new medicine. Returns the new id."""
    row = db.execute(
        text(
            """
            INSERT INTO medicine_component_lookup (
                medicine_key, medicine_name, components, subclassification,
                is_high_end_antibiotic, source, last_checked_at
            ) VALUES (
                :medicine_key, :medicine_name, :components, :subclassification,
                :is_high_end_antibiotic, :source, NOW()
            )
            RETURNING id
            """
        ),
        params,
    ).first()
    return int(row[0])


def update_medicine(db: Session, medicine_id: int, params: dict[str, Any]) -> int | None:
    """Update a medicine by id. Returns the id if found."""
    row = db.execute(
        text(
            """
            UPDATE medicine_component_lookup
            SET medicine_key = :medicine_key,
                medicine_name = :medicine_name,
                components = :components,
                subclassification = :subclassification,
                is_high_end_antibiotic = :is_high_end_antibiotic,
                source = :source,
                last_checked_at = NOW()
            WHERE id = :id
            RETURNING id
            """
        ),
        {**params, "id": medicine_id},
    ).first()
    return int(row[0]) if row else None


def delete_medicine(db: Session, medicine_id: int) -> dict[str, Any] | None:
    """Delete a medicine by id. Returns the deleted row or None."""
    row = db.execute(
        text(
            """
            DELETE FROM medicine_component_lookup
            WHERE id = :id
            RETURNING id
            """
        ),
        {"id": medicine_id},
    ).mappings().first()
    return dict(row) if row else None


def lookup_medicine_by_name(db: Session, medicine_name: str) -> dict[str, Any] | None:
    """Look up a medicine by name for catalog resolution."""
    row = db.execute(
        text(
            """
            SELECT id, medicine_key, medicine_name, components, subclassification,
                   is_high_end_antibiotic
            FROM medicine_component_lookup
            WHERE medicine_name ILIKE :name
            LIMIT 1
            """
        ),
        {"name": medicine_name},
    ).mappings().first()
    return dict(row) if row else None


def load_high_end_antibiotic_catalog(db: Session, antibiotic_names: list[str]) -> list[dict[str, Any]]:
    """Load high-end antibiotic entries from the medicine catalog."""
    like_params: dict[str, Any] = {}
    clauses: list[str] = ["is_high_end_antibiotic = TRUE"]
    for idx, name in enumerate(antibiotic_names):
        key = f"h{idx}"
        clauses.append(f"LOWER(COALESCE(components, '')) LIKE :{key}")
        like_params[key] = "%" + name.lower() + "%"

    sql = (
        "SELECT medicine_name, components, is_high_end_antibiotic "
        "FROM medicine_component_lookup "
        + "WHERE " + " OR ".join(clauses) + " "
        + "ORDER BY medicine_name ASC"
    )

    try:
        rows = db.execute(text(sql), like_params).mappings().all()
    except Exception:
        return []
    return [dict(r) for r in rows]
