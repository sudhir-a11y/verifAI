from __future__ import annotations

import json
import math
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.extraction import ExtractionConfigError, ExtractionProcessingError, run_extraction
from app.infrastructure.storage.storage_service import StorageConfigError, StorageOperationError, download_bytes
from app.repositories import claim_documents_repo, document_extractions_repo, workflow_events_repo
from app.schemas.extraction import ExtractionListResponse, ExtractionProvider, ExtractionResponse


class DocumentNotFoundError(Exception):
    pass


def _normalize_json(value: Any, as_type: type) -> Any:
    if isinstance(value, as_type):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, as_type) else as_type()
        except json.JSONDecodeError:
            return as_type()
    return as_type()


def _to_response(row: dict[str, Any]) -> ExtractionResponse:
    row["extracted_entities"] = _normalize_json(row.get("extracted_entities"), dict)
    row["evidence_refs"] = _normalize_json(row.get("evidence_refs"), list)

    raw_response = row.get("raw_response")
    if isinstance(raw_response, dict):
        row["raw_response"] = raw_response
    elif isinstance(raw_response, str):
        try:
            parsed_raw = json.loads(raw_response)
            row["raw_response"] = parsed_raw if isinstance(parsed_raw, dict) else None
        except json.JSONDecodeError:
            row["raw_response"] = None
    else:
        row["raw_response"] = None

    return ExtractionResponse.model_validate(row)


def _sanitize_json_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _sanitize_json_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_json_payload(v) for v in value]
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
    return value


def run_document_extraction(
    db: Session,
    document_id: UUID,
    provider: ExtractionProvider,
    actor_id: str | None,
    force_refresh: bool = False,
) -> ExtractionResponse:
    doc = claim_documents_repo.get_document_row_by_id(db, document_id=str(document_id))
    if doc is None:
        raise DocumentNotFoundError

    claim_id = UUID(str(doc["claim_id"]))
    doc_metadata = _normalize_json(doc.get("metadata"), dict)
    resolved_s3_bucket = str(doc_metadata.get("bucket") or doc_metadata.get("legacy_s3_bucket") or "").strip() or None
    storage_key = str(doc.get("storage_key") or "").strip()

    if force_refresh:
        document_extractions_repo.delete_by_claim_and_document(db, str(claim_id), str(document_id))

    claim_documents_repo.update_parse_status(db, str(document_id), "processing")
    db.commit()

    try:
        payload = download_bytes(storage_key)
        extraction_data = run_extraction(
            provider=provider,
            document_name=doc["file_name"],
            mime_type=doc["mime_type"],
            payload=payload,
            storage_key=storage_key or None,
            s3_bucket=resolved_s3_bucket,
        )

        extraction_version = f"{extraction_data['extraction_version']}-{uuid4().hex[:8]}"

        row = document_extractions_repo.insert_extraction_returning_row(
            db,
            claim_id=str(claim_id),
            document_id=str(document_id),
            extraction_version=extraction_version,
            model_name=extraction_data["model_name"],
            extracted_entities=_sanitize_json_payload(extraction_data["extracted_entities"]),
            evidence_refs=_sanitize_json_payload(extraction_data["evidence_refs"]),
            confidence=extraction_data.get("confidence"),
            created_by=actor_id or extraction_data["provider"],
        )

        claim_documents_repo.update_parse_status(db, str(document_id), "succeeded")

        workflow_events_repo.emit_workflow_event(
            db,
            claim_id,
            event_type="document_extracted",
            actor_id=actor_id,
            payload={
                "document_id": str(document_id),
                "extraction_id": str(row.get("id") or ""),
                "provider": extraction_data["provider"],
                "model_name": extraction_data["model_name"],
            },
        )

        db.commit()
        response_row = dict(row)
        raw_response = extraction_data.get("raw_response")
        if isinstance(raw_response, dict):
            response_row["raw_response"] = _sanitize_json_payload(raw_response)
        return _to_response(response_row)
    except (StorageConfigError, StorageOperationError, ExtractionConfigError, ExtractionProcessingError, SQLAlchemyError, Exception) as exc:
        db.rollback()
        try:
            claim_documents_repo.update_parse_status(db, str(document_id), "failed")
            workflow_events_repo.emit_workflow_event(
                db,
                claim_id,
                event_type="document_extraction_failed",
                actor_id=actor_id,
                payload={
                    "document_id": str(document_id),
                    "provider": provider.value,
                    "error": str(exc),
                },
            )
            db.commit()
        except SQLAlchemyError:
            db.rollback()

        if isinstance(exc, SQLAlchemyError):
            raise ExtractionProcessingError(f"database write failed: {exc}") from exc
        if isinstance(exc, (StorageConfigError, StorageOperationError, ExtractionConfigError, ExtractionProcessingError)):
            raise
        raise ExtractionProcessingError(f"unexpected extraction error: {exc}") from exc


def list_document_extractions(db: Session, document_id: UUID, limit: int, offset: int) -> ExtractionListResponse:
    doc = claim_documents_repo.get_document_row_by_id(db, document_id=str(document_id))
    if doc is None:
        raise DocumentNotFoundError

    rows, total = document_extractions_repo.list_extractions_by_document_id(
        db,
        document_id=str(document_id),
        limit=limit,
        offset=offset,
    )
    return ExtractionListResponse(total=total, items=[_to_response(r) for r in rows])
