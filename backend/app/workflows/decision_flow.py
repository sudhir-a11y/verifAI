from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories import decision_results_repo


def get_latest_decision_for_claim(db: Session, *, claim_id: UUID) -> dict[str, Any] | None:
    return decision_results_repo.get_latest_decision_for_claim(db, claim_id)

