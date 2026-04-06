from sqlalchemy import text
from sqlalchemy.orm import Session


def reset_parse_status(db: Session, *, claim_id: str) -> int:
    return int(
        db.execute(
            text(
                """
                UPDATE claim_documents
                SET parse_status = 'pending',
                    parsed_at = NULL
                WHERE claim_id = :claim_id
                """
            ),
            {"claim_id": claim_id},
        ).rowcount
        or 0
    )

