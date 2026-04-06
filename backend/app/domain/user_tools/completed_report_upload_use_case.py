from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.user_tools.completed_reports_use_case import TAGGING_SUBTAGGING_OPTIONS
from app.repositories import claim_report_uploads_repo, claims_repo, workflow_events_repo
from app.schemas.qc_tools import CompletedReportUploadStatusResponse


class InvalidUploadPayloadError(ValueError):
    pass


class CompletedClaimNotFoundError(RuntimeError):
    pass


def _normalize_optional_text(value: str | None) -> str:
    return str(value or "").strip()


def _normalize_tagging(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "genuine":
        return "Genuine"
    if normalized in {"fraudulent", "fraudlent"}:
        return "Fraudulent"
    return ""


def _normalize_subtagging(tagging: str, value: str | None) -> str:
    options = TAGGING_SUBTAGGING_OPTIONS.get(tagging, [])
    raw = str(value or "").strip()
    if not raw:
        return ""
    for option in options:
        if raw.lower() == option.lower():
            return option
    return ""


def update_completed_report_upload_status(
    db: Session,
    *,
    claim_id: UUID,
    report_export_status: str | None,
    tagging: str | None,
    subtagging: str | None,
    opinion: str | None,
    actor_username: str,
) -> CompletedReportUploadStatusResponse:
    claim_report_uploads_repo.ensure_claim_report_uploads_table(db)

    target_status = (report_export_status or "uploaded").strip().lower()
    normalized_tagging = _normalize_tagging(tagging)
    normalized_subtagging = _normalize_subtagging(normalized_tagging, subtagging)
    normalized_opinion = _normalize_optional_text(opinion)

    if target_status != "uploaded":
        raise InvalidUploadPayloadError("Please select Uploaded status before saving.")
    if not normalized_tagging or not normalized_subtagging or not normalized_opinion:
        raise InvalidUploadPayloadError("Tagging, Subtagging and Opinion are mandatory.")

    external_claim_id = claims_repo.get_completed_claim_external_id(db, claim_id=claim_id)
    if not external_claim_id:
        raise CompletedClaimNotFoundError("Completed claim not found.")

    row = claim_report_uploads_repo.upsert_upload_status(
        db,
        claim_id=str(claim_id),
        report_export_status="uploaded",
        tagging=normalized_tagging,
        subtagging=normalized_subtagging,
        opinion=normalized_opinion,
        updated_by=actor_username,
    )

    workflow_events_repo.emit_workflow_event(
        db=db,
        claim_id=claim_id,
        event_type="completed_report_upload_status_updated",
        actor_id=actor_username,
        payload={"report_export_status": "uploaded", "tagging": normalized_tagging, "subtagging": normalized_subtagging},
    )

    db.commit()

    return CompletedReportUploadStatusResponse(
        claim_id=str(row.get("claim_id") or claim_id),
        external_claim_id=str(external_claim_id),
        report_export_status=str(row.get("report_export_status") or "uploaded"),
        tagging=_normalize_optional_text(row.get("tagging")),
        subtagging=_normalize_optional_text(row.get("subtagging")),
        opinion=_normalize_optional_text(row.get("opinion")),
        updated_at=str(row.get("updated_at") or ""),
    )


__all__ = [
    "CompletedClaimNotFoundError",
    "InvalidUploadPayloadError",
    "update_completed_report_upload_status",
]

