from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.documents.documents_use_cases import list_documents
from app.domain.extractions.use_cases import run_document_extraction
from app.schemas.extraction import ExtractionProvider


def extract_all_documents_for_claim(
    db: Session,
    *,
    claim_id: UUID,
    actor_id: str,
    provider: ExtractionProvider,
    force_refresh: bool = False,
    limit: int = 500,
) -> int:
    docs = list_documents(db, claim_id, limit=int(limit or 500), offset=0)
    doc_items = getattr(docs, "items", None) or []

    extracted = 0
    for doc in doc_items:
        doc_id = getattr(doc, "id", None)
        if doc_id is None:
            continue
        run_document_extraction(
            db,
            document_id=doc_id,
            provider=provider,
            actor_id=actor_id,
            force_refresh=bool(force_refresh),
        )
        extracted += 1
    return extracted

