from sqlalchemy import text
from sqlalchemy.orm import Session


def delete_by_claim_id(db: Session, *, claim_id: str) -> int:
    return int(
        db.execute(text("DELETE FROM document_extractions WHERE claim_id = :claim_id"), {"claim_id": claim_id}).rowcount
        or 0
    )

