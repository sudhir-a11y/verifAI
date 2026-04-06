from uuid import UUID
import re

from sqlalchemy.orm import Session

from app.repositories import claim_documents_repo, claims_repo


def parse_assigned_doctors(value: str | None) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part and part.strip()]


def _normalize_doctor_token(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "", raw)


def doctor_matches_assignment(assigned_doctor_id: str | None, doctor_username: str) -> bool:
    doctors = parse_assigned_doctors(assigned_doctor_id)
    target = _normalize_doctor_token(doctor_username)
    if not target:
        return False
    return any(_normalize_doctor_token(doc) == target for doc in doctors)


def doctor_can_access_claim(db: Session, claim_id: UUID, doctor_username: str) -> bool | None:
    assigned = claims_repo.get_claim_assigned_doctor_id(db, claim_id=claim_id)
    if assigned is None:
        return None
    return doctor_matches_assignment(assigned, doctor_username)


def doctor_can_access_document(db: Session, document_id: UUID, doctor_username: str) -> bool | None:
    assigned = claim_documents_repo.get_assigned_doctor_id_for_document(db, str(document_id))
    if assigned is None:
        return None
    return doctor_matches_assignment(assigned, doctor_username)
