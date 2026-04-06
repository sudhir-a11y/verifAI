from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def count_medicines(db: Session, *, search: str | None) -> int:
    where = ""
    params: dict[str, Any] = {}
    if search and str(search).strip():
        where = "WHERE medicine_key ILIKE :q OR medicine_name ILIKE :q OR components ILIKE :q"
        params["q"] = f"%{str(search).strip()}%"
    total = db.execute(text(f"SELECT COUNT(*) FROM medicine_component_lookup {where}"), params).scalar_one()
    return int(total or 0)


def list_medicines(db: Session, *, search: str | None, limit: int, offset: int) -> list[dict[str, Any]]:
    where = ""
    params: dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
    if search and str(search).strip():
        where = "WHERE medicine_key ILIKE :q OR medicine_name ILIKE :q OR components ILIKE :q"
        params["q"] = f"%{str(search).strip()}%"

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
    return [dict(row) for row in rows]


def insert_medicine(
    db: Session,
    *,
    medicine_key: str,
    medicine_name: str,
    components: str,
    subclassification: str,
    is_high_end_antibiotic: bool,
    source: str,
) -> int:
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
        {
            "medicine_key": medicine_key,
            "medicine_name": medicine_name,
            "components": components,
            "subclassification": subclassification,
            "is_high_end_antibiotic": bool(is_high_end_antibiotic),
            "source": source,
        },
    ).mappings().one()
    return int(row["id"])


def update_medicine(
    db: Session,
    *,
    medicine_id: int,
    medicine_key: str,
    medicine_name: str,
    components: str,
    subclassification: str,
    is_high_end_antibiotic: bool,
    source: str,
) -> dict[str, Any] | None:
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
        {
            "id": int(medicine_id),
            "medicine_key": medicine_key,
            "medicine_name": medicine_name,
            "components": components,
            "subclassification": subclassification,
            "is_high_end_antibiotic": bool(is_high_end_antibiotic),
            "source": source,
        },
    ).mappings().first()
    return dict(row) if row is not None else None


def delete_medicine(db: Session, *, medicine_id: int) -> bool:
    row = db.execute(
        text(
            """
            DELETE FROM medicine_component_lookup
            WHERE id = :id
            RETURNING id
            """
        ),
        {"id": int(medicine_id)},
    ).mappings().first()
    return row is not None

