from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.document import (
    DocumentBulkDeleteResponse,
    DocumentListResponse,
    DocumentParseStatusUpdateRequest,
    DocumentResponse,
)
from app.domain.documents.use_cases import (
    ClaimNotFoundError,
    DocumentMergeError,
    DocumentNotFoundError,
    create_document as _create_document,
    create_merged_document as _create_merged_document,
    delete_documents as _delete_documents,
    get_document_download_url as _get_document_download_url,
    list_documents as _list_documents,
    update_document_parse_status as _update_document_parse_status,
)


def create_document(
    db: Session,
    *,
    claim_id: UUID,
    file_name: str,
    mime_type: str,
    file_bytes: bytes,
    uploaded_by: str,
    retention_class: str,
    compression_mode: str,
) -> DocumentResponse:
    return _create_document(
        db=db,
        claim_id=claim_id,
        file_name=file_name,
        mime_type=mime_type,
        file_bytes=file_bytes,
        uploaded_by=uploaded_by,
        retention_class=retention_class,
        compression_mode=compression_mode,
    )


def create_merged_document(
    db: Session,
    *,
    claim_id: UUID,
    file_items: list[dict],
    uploaded_by: str,
    retention_class: str,
    compression_mode: str,
):
    return _create_merged_document(
        db=db,
        claim_id=claim_id,
        file_items=file_items,
        uploaded_by=uploaded_by,
        retention_class=retention_class,
        compression_mode=compression_mode,
    )


def list_documents(db: Session, claim_id: UUID, limit: int, offset: int) -> DocumentListResponse:
    return _list_documents(db, claim_id, limit, offset)


def delete_documents(
    db: Session,
    *,
    claim_id: UUID,
    document_ids: list[UUID],
    actor_id: str,
) -> DocumentBulkDeleteResponse:
    return _delete_documents(db=db, claim_id=claim_id, document_ids=document_ids, actor_id=actor_id)


def update_document_parse_status(
    db: Session,
    document_id: UUID,
    payload: DocumentParseStatusUpdateRequest,
) -> DocumentResponse:
    return _update_document_parse_status(db, document_id, payload)


def get_document_download_url(db: Session, document_id: UUID, expires_in: int):
    return _get_document_download_url(db, document_id, expires_in)
