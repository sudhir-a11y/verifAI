import mimetypes
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps.auth import require_roles
from app.db.session import SessionLocal, get_db
from app.schemas.auth import UserRole
from app.schemas.document import (
    DocumentBulkDeleteRequest,
    DocumentBulkDeleteResponse,
    DocumentDownloadUrlResponse,
    DocumentListResponse,
    DocumentMergeUploadResponse,
    DocumentParseStatusUpdateRequest,
    DocumentResponse,
)
from app.domain.documents.documents_use_cases import (
    ClaimNotFoundError,
    DocumentMergeError,
    DocumentNotFoundError,
    create_document,
    create_merged_document,
    delete_documents,
    get_document_download_url,
    list_documents,
    update_document_parse_status,
)
from app.dependencies.access_control import doctor_can_access_claim, doctor_can_access_document
from app.domain.auth.service import AuthenticatedUser
from app.domain.claims.events import try_record_workflow_event
from app.infrastructure.storage.storage_service import StorageConfigError, StorageOperationError
from app.workflows.prepare_flow import prepare_claim_for_ai

router = APIRouter(tags=["documents"])


def _run_claim_prepare_background(claim_id: UUID, actor_id: str) -> None:
    db = SessionLocal()
    try:
        prepare_claim_for_ai(
            db=db,
            claim_id=claim_id,
            actor_id=actor_id,
            force_refresh=False,
            use_llm=False,
        )
    except Exception as exc:
        try_record_workflow_event(
            db,
            claim_id=claim_id,
            actor_id=actor_id,
            event_type="claim_prepare_failed",
            payload={"error": str(exc), "error_type": type(exc).__name__, "source": "document_upload_background"},
        )
    finally:
        db.close()


@router.post(
    "/claims/{claim_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document_endpoint(
    claim_id: UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    uploaded_by: str | None = Form(default=None),
    retention_class: str = Form(default="standard"),
    compression_mode: str = Form(default="lossy"),
    auto_prepare_ai: bool = Form(default=True),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user)),
) -> DocumentResponse:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file upload")

    guessed_mime_type, _ = mimetypes.guess_type(file.filename or "")
    mime_type = file.content_type or guessed_mime_type or "application/octet-stream"

    try:
        created = create_document(
            db=db,
            claim_id=claim_id,
            file_name=file.filename or "document",
            mime_type=mime_type,
            file_bytes=content,
            uploaded_by=uploaded_by or current_user.username,
            retention_class=retention_class,
            compression_mode=compression_mode,
        )
        if bool(auto_prepare_ai) and background_tasks is not None:
            background_tasks.add_task(_run_claim_prepare_background, claim_id, uploaded_by or current_user.username)
        return created
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc
    except StorageConfigError as exc:
        raise HTTPException(status_code=500, detail=f"storage config error: {exc}") from exc
    except StorageOperationError as exc:
        raise HTTPException(status_code=502, detail=f"storage operation error: {exc}") from exc


@router.post(
    "/claims/{claim_id}/documents/merged",
    response_model=DocumentMergeUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_merged_document_endpoint(
    claim_id: UUID,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    uploaded_by: str | None = Form(default=None),
    retention_class: str = Form(default="standard"),
    compression_mode: str = Form(default="lossy"),
    auto_prepare_ai: bool = Form(default=True),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user)),
) -> DocumentMergeUploadResponse:
    if not files:
        raise HTTPException(status_code=400, detail="no files received")

    file_items: list[dict] = []
    for file in files:
        content = await file.read()
        if not content:
            continue
        guessed_mime_type, _ = mimetypes.guess_type(file.filename or "")
        mime_type = file.content_type or guessed_mime_type or "application/octet-stream"
        file_items.append(
            {
                "file_name": file.filename or "document",
                "mime_type": mime_type,
                "file_bytes": content,
            }
        )

    if not file_items:
        raise HTTPException(status_code=400, detail="all files are empty")

    try:
        document, accepted_files, skipped_files, source_total_size_bytes, output_size_bytes, saved_size_bytes, compression_ratio = create_merged_document(
            db=db,
            claim_id=claim_id,
            file_items=file_items,
            uploaded_by=uploaded_by or current_user.username,
            retention_class=retention_class,
            compression_mode=compression_mode,
        )
        response = DocumentMergeUploadResponse(
            document=document,
            source_file_count=len(file_items),
            accepted_file_count=len(accepted_files),
            skipped_file_count=len(skipped_files),
            accepted_files=accepted_files,
            skipped_files=skipped_files,
            merged_source_total_size_bytes=source_total_size_bytes,
            merged_output_size_bytes=output_size_bytes,
            merged_saved_size_bytes=saved_size_bytes,
            merge_compression_ratio=compression_ratio,
        )
        if bool(auto_prepare_ai) and background_tasks is not None:
            background_tasks.add_task(_run_claim_prepare_background, claim_id, uploaded_by or current_user.username)
        return response
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc
    except DocumentMergeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StorageConfigError as exc:
        raise HTTPException(status_code=500, detail=f"storage config error: {exc}") from exc
    except StorageOperationError as exc:
        raise HTTPException(status_code=502, detail=f"storage operation error: {exc}") from exc


@router.get("/claims/{claim_id}/documents", response_model=DocumentListResponse)
def list_documents_endpoint(
    claim_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)),
) -> DocumentListResponse:
    if current_user.role == UserRole.doctor:
        allowed = doctor_can_access_claim(db, claim_id, current_user.username)
        if allowed is False:
            raise HTTPException(status_code=403, detail="doctor can access only assigned claims")

    try:
        return list_documents(db, claim_id, limit, offset)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc


@router.delete("/claims/{claim_id}/documents", response_model=DocumentBulkDeleteResponse)
def delete_documents_endpoint(
    claim_id: UUID,
    payload: DocumentBulkDeleteRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user)),
) -> DocumentBulkDeleteResponse:
    try:
        return delete_documents(
            db=db,
            claim_id=claim_id,
            document_ids=payload.document_ids,
            actor_id=payload.actor_id or current_user.username,
        )
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc


@router.patch("/documents/{document_id}/parse-status", response_model=DocumentResponse)
def update_document_parse_status_endpoint(
    document_id: UUID,
    payload: DocumentParseStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.doctor)),
) -> DocumentResponse:
    if current_user.role == UserRole.doctor:
        allowed = doctor_can_access_document(db, document_id, current_user.username)
        if allowed is False:
            raise HTTPException(status_code=403, detail="doctor can access only assigned claim documents")

    enriched_payload = payload.model_copy(update={"actor_id": payload.actor_id or current_user.username})

    try:
        return update_document_parse_status(db, document_id, enriched_payload)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="document not found") from exc


@router.get("/documents/{document_id}/download-url", response_model=DocumentDownloadUrlResponse)
def get_document_download_url_endpoint(
    document_id: UUID,
    expires_in: int = Query(default=900, ge=60, le=86400),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)),
) -> DocumentDownloadUrlResponse:
    if current_user.role == UserRole.doctor:
        allowed = doctor_can_access_document(db, document_id, current_user.username)
        if allowed is False:
            raise HTTPException(status_code=403, detail="doctor can access only assigned claim documents")

    try:
        return get_document_download_url(db, document_id, expires_in)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="document not found") from exc
    except StorageConfigError as exc:
        raise HTTPException(status_code=500, detail=f"storage config error: {exc}") from exc
    except StorageOperationError as exc:
        raise HTTPException(status_code=502, detail=f"storage operation error: {exc}") from exc
