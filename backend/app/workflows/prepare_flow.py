from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.structuring import (
    ClaimStructuredDataNotFoundError,
    generate_claim_structured_data,
    get_claim_structured_data,
)
from app.domain.checklist.checklist_use_cases import evaluate_claim_checklist, get_latest_claim_checklist
from app.domain.claims.events import try_record_workflow_event
from app.repositories import workflow_job_locks_repo
from app.schemas.extraction import ExtractionProvider
from app.workflows.claim_freshness import is_artifact_fresh_for_claim
from app.workflows.extraction_flow import extract_all_documents_for_claim


@dataclass(frozen=True)
class ClaimPrepareResult:
    claim_id: UUID
    lock_acquired: bool
    extracted_documents: int
    structured_generated: bool
    checklist_ran: bool


def _coerce_datetime(value: object) -> datetime | None:
    return value if isinstance(value, datetime) else None


def prepare_claim_for_ai(
    db: Session,
    *,
    claim_id: UUID,
    actor_id: str,
    force_refresh: bool = False,
    use_llm: bool = False,
) -> ClaimPrepareResult:
    actor = str(actor_id or "system:prepare").strip() or "system:prepare"
    lock_owner = f"{actor}:prepare"
    acquired = workflow_job_locks_repo.acquire_lock(
        db,
        claim_id=claim_id,
        job_type="claim_prepare",
        locked_by=lock_owner,
        ttl_seconds=900,
    )
    db.commit()

    if not acquired:
        try_record_workflow_event(
            db,
            claim_id=claim_id,
            actor_id=actor,
            event_type="claim_prepare_skipped_locked",
            payload={},
        )
        return ClaimPrepareResult(
            claim_id=claim_id,
            lock_acquired=False,
            extracted_documents=0,
            structured_generated=False,
            checklist_ran=False,
        )

    extracted_documents = 0
    structured_generated = False
    checklist_ran = False
    try:
        try_record_workflow_event(
            db,
            claim_id=claim_id,
            actor_id=actor,
            event_type="claim_prepare_started",
            payload={"force_refresh": bool(force_refresh), "use_llm": bool(use_llm)},
        )

        extracted_documents = extract_all_documents_for_claim(
            db,
            claim_id=claim_id,
            actor_id=actor,
            provider=ExtractionProvider.hybrid_local,
            force_refresh=bool(force_refresh),
            best_effort=True,
        )

        structured = None
        try:
            structured = get_claim_structured_data(db, claim_id)
        except ClaimStructuredDataNotFoundError:
            structured = None
        except Exception:
            structured = None

        structured_is_fresh = False
        if isinstance(structured, dict):
            structured_is_fresh = is_artifact_fresh_for_claim(
                db,
                claim_id=claim_id,
                artifact_generated_at=_coerce_datetime(structured.get("updated_at")),
            )

        if force_refresh or (structured is None) or (not structured_is_fresh):
            generate_claim_structured_data(
                db=db,
                claim_id=claim_id,
                actor_id=actor,
                use_llm=bool(use_llm),
                force_refresh=True,
            )
            structured_generated = True

        checklist_latest = get_latest_claim_checklist(db=db, claim_id=claim_id)
        checklist_fresh = is_artifact_fresh_for_claim(
            db,
            claim_id=claim_id,
            artifact_generated_at=_coerce_datetime(getattr(checklist_latest, "generated_at", None)),
        ) if getattr(checklist_latest, "found", False) else False

        if force_refresh or (not checklist_latest.found) or (not checklist_fresh):
            evaluate_claim_checklist(
                db=db,
                claim_id=claim_id,
                actor_id=actor,
                force_source_refresh=False,
            )
            checklist_ran = True

        try_record_workflow_event(
            db,
            claim_id=claim_id,
            actor_id=actor,
            event_type="claim_prepare_completed",
            payload={
                "extracted_documents": int(extracted_documents),
                "structured_generated": bool(structured_generated),
                "checklist_ran": bool(checklist_ran),
            },
        )
        return ClaimPrepareResult(
            claim_id=claim_id,
            lock_acquired=True,
            extracted_documents=int(extracted_documents),
            structured_generated=bool(structured_generated),
            checklist_ran=bool(checklist_ran),
        )
    except Exception as exc:
        try_record_workflow_event(
            db,
            claim_id=claim_id,
            actor_id=actor,
            event_type="claim_prepare_failed",
            payload={"error": str(exc), "error_type": type(exc).__name__},
        )
        raise
    finally:
        try:
            workflow_job_locks_repo.release_lock(
                db,
                claim_id=claim_id,
                job_type="claim_prepare",
                locked_by=lock_owner,
            )
            db.commit()
        except Exception:
            db.rollback()
