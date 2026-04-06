from __future__ import annotations

import json
import math
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.extraction_providers import ExtractionConfigError, ExtractionProcessingError, run_extraction
from app.infrastructure.storage.storage_service import StorageConfigError, StorageOperationError, download_bytes
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


def _emit_workflow_event(
    db: Session,
    claim_id: UUID,
    event_type: str,
    actor_id: str | None,
    payload: dict[str, Any],
) -> None:
    db.execute(
        text(
            """
            INSERT INTO workflow_events (claim_id, actor_type, actor_id, event_type, event_payload)
            VALUES (:claim_id, 'user', :actor_id, :event_type, CAST(:event_payload AS jsonb))
            """
        ),
        {
            "claim_id": str(claim_id),
            "actor_id": actor_id,
            "event_type": event_type,
            "event_payload": json.dumps(payload),
        },
    )


def run_document_extraction(
    db: Session,
    document_id: UUID,
    provider: ExtractionProvider,
    actor_id: str | None,
    force_refresh: bool = False,
) -> ExtractionResponse:
    doc = db.execute(
        text(
            """
            SELECT id, claim_id, storage_key, file_name, mime_type, metadata
            FROM claim_documents
            WHERE id = :document_id
            """
        ),
        {"document_id": str(document_id)},
    ).mappings().first()

    if doc is None:
        raise DocumentNotFoundError

    claim_id = doc["claim_id"]
    doc_metadata = _normalize_json(doc.get("metadata"), dict)
    resolved_s3_bucket = str(doc_metadata.get("bucket") or doc_metadata.get("legacy_s3_bucket") or "").strip() or None
    storage_key = str(doc.get("storage_key") or "").strip()

    if force_refresh:
        db.execute(
            text("DELETE FROM document_extractions WHERE claim_id = :claim_id AND document_id = :document_id"),
            {"claim_id": str(claim_id), "document_id": str(document_id)},
        )

    db.execute(
        text("UPDATE claim_documents SET parse_status = 'processing' WHERE id = :document_id"),
        {"document_id": str(document_id)},
    )
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

        row = db.execute(
            text(
                """
                INSERT INTO document_extractions (
                    claim_id,
                    document_id,
                    extraction_version,
                    model_name,
                    extracted_entities,
                    evidence_refs,
                    confidence,
                    created_by
                )
                VALUES (
                    :claim_id,
                    :document_id,
                    :extraction_version,
                    :model_name,
                    CAST(:extracted_entities AS jsonb),
                    CAST(:evidence_refs AS jsonb),
                    :confidence,
                    :created_by
                )
                RETURNING
                    id,
                    claim_id,
                    document_id,
                    extraction_version,
                    model_name,
                    extracted_entities,
                    evidence_refs,
                    confidence,
                    created_by,
                    created_at
                """
            ),
            {
                "claim_id": str(claim_id),
                "document_id": str(document_id),
                "extraction_version": extraction_version,
                "model_name": extraction_data["model_name"],
                "extracted_entities": json.dumps(
                    _sanitize_json_payload(extraction_data["extracted_entities"]),
                    ensure_ascii=False,
                    allow_nan=False,
                ),
                "evidence_refs": json.dumps(
                    _sanitize_json_payload(extraction_data["evidence_refs"]),
                    ensure_ascii=False,
                    allow_nan=False,
                ),
                "confidence": extraction_data.get("confidence"),
                "created_by": actor_id or extraction_data["provider"],
            },
        ).mappings().one()

        db.execute(
            text("UPDATE claim_documents SET parse_status = 'succeeded', parsed_at = NOW() WHERE id = :document_id"),
            {"document_id": str(document_id)},
        )

        _emit_workflow_event(
            db=db,
            claim_id=claim_id,
            event_type="document_extracted",
            actor_id=actor_id,
            payload={
                "document_id": str(document_id),
                "extraction_id": str(row["id"]),
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
            db.execute(
                text("UPDATE claim_documents SET parse_status = 'failed' WHERE id = :document_id"),
                {"document_id": str(document_id)},
            )
            _emit_workflow_event(
                db=db,
                claim_id=claim_id,
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
    params = {"document_id": str(document_id), "limit": limit, "offset": offset}

    exists = db.execute(
        text("SELECT 1 FROM claim_documents WHERE id = :document_id"),
        params,
    ).first()
    if exists is None:
        raise DocumentNotFoundError

    total = db.execute(
        text("SELECT COUNT(*) FROM document_extractions WHERE document_id = :document_id"),
        params,
    ).scalar_one()

    rows = db.execute(
        text(
            """
            SELECT
                id,
                claim_id,
                document_id,
                extraction_version,
                model_name,
                extracted_entities,
                evidence_refs,
                confidence,
                created_by,
                created_at
            FROM document_extractions
            WHERE document_id = :document_id
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()

    return ExtractionListResponse(total=total, items=[_to_response(dict(r)) for r in rows])

