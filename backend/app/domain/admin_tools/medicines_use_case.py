from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.admin_tools.normalization import medicine_key
from app.repositories import admin_medicines_repo


@dataclass(frozen=True)
class InvalidMedicineNameError(Exception):
    message: str = "invalid medicine_name"


@dataclass(frozen=True)
class MedicineAlreadyExistsError(Exception):
    message: str = "medicine already exists"


@dataclass(frozen=True)
class MedicineNotFoundError(Exception):
    message: str = "medicine not found"


def list_medicines(
    db: Session,
    *,
    search: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    total = admin_medicines_repo.count_medicines(db, search=search)
    rows = admin_medicines_repo.list_medicines(db, search=search, limit=limit, offset=offset)

    items: list[dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "id": int(row["id"]),
                "medicine_key": str(row.get("medicine_key") or ""),
                "medicine_name": str(row.get("medicine_name") or ""),
                "components": str(row.get("components") or ""),
                "subclassification": str(row.get("subclassification") or ""),
                "is_high_end_antibiotic": bool(row.get("is_high_end_antibiotic")),
                "source": str(row.get("source") or "table"),
                "updated_at": row.get("updated_at"),
            }
        )
    return {"total": total, "items": items}


def create_medicine(
    db: Session,
    *,
    payload,
    created_by_username: str,
) -> dict[str, Any]:
    key = medicine_key(payload.medicine_name)
    if not key:
        raise InvalidMedicineNameError()

    try:
        row_id = admin_medicines_repo.insert_medicine(
            db,
            medicine_key=key,
            medicine_name=payload.medicine_name.strip(),
            components=payload.components.strip(),
            subclassification=payload.subclassification.strip() or "Supportive care",
            is_high_end_antibiotic=bool(payload.is_high_end_antibiotic),
            source=f"manual:{created_by_username}",
        )
    except IntegrityError as exc:
        raise MedicineAlreadyExistsError() from exc

    return {"id": int(row_id), "message": "medicine created"}


def update_medicine(
    db: Session,
    *,
    medicine_id: int,
    payload,
    updated_by_username: str,
) -> dict[str, Any]:
    key = medicine_key(payload.medicine_name)
    if not key:
        raise InvalidMedicineNameError()

    try:
        row = admin_medicines_repo.update_medicine(
            db,
            medicine_id=medicine_id,
            medicine_key=key,
            medicine_name=payload.medicine_name.strip(),
            components=payload.components.strip(),
            subclassification=payload.subclassification.strip() or "Supportive care",
            is_high_end_antibiotic=bool(payload.is_high_end_antibiotic),
            source=f"manual:{updated_by_username}",
        )
    except IntegrityError as exc:
        raise MedicineAlreadyExistsError("medicine key conflict") from exc

    if row is None:
        raise MedicineNotFoundError()
    return {"id": int(row["id"]), "message": "medicine updated"}


def delete_medicine(db: Session, *, medicine_id: int) -> dict[str, Any]:
    ok = admin_medicines_repo.delete_medicine(db, medicine_id=medicine_id)
    if not ok:
        raise MedicineNotFoundError()
    return {"id": int(medicine_id), "message": "medicine deleted"}

