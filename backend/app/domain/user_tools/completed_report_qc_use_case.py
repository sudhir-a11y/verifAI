from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.ml import AUDITOR_QC_LABEL_TYPE, recommendation_to_feedback_label, upsert_feedback_label
from app.repositories import claim_report_uploads_repo, claims_repo, decision_results_repo, workflow_events_repo
from app.schemas.qc_tools import CompletedReportQcStatusResponse


class InvalidQcStatusError(ValueError):
    pass


class CompletedClaimNotFoundError(RuntimeError):
    pass


def _normalize_qc_status(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "no"
    compact = raw.replace("-", "_").replace(" ", "_")
    if compact in {"yes", "qc_yes", "qcyes", "qc_done", "done"}:
        return "yes"
    if compact in {"no", "qc_no", "qcno", "pending", "not_done"}:
        return "no"
    return ""


def update_completed_report_qc_status(
    db: Session,
    *,
    claim_id: UUID,
    qc_status: str | None,
    actor_username: str,
) -> CompletedReportQcStatusResponse:
    claim_report_uploads_repo.ensure_claim_report_uploads_table(db)

    normalized_qc = _normalize_qc_status(qc_status) or ""
    if normalized_qc not in {"yes", "no"}:
        raise InvalidQcStatusError("Invalid QC status selected.")

    external_claim_id = claims_repo.get_completed_claim_external_id(db, claim_id=claim_id)
    if not external_claim_id:
        raise CompletedClaimNotFoundError("Completed claim not found.")

    row = claim_report_uploads_repo.upsert_qc_status(
        db,
        claim_id=str(claim_id),
        qc_status=normalized_qc,
        updated_by=actor_username,
    )

    feedback_label_value: str | None = None
    feedback_decision_id: str | None = None
    latest_decision = decision_results_repo.get_latest_decision_for_claim(db, claim_id)

    if latest_decision is not None:
        feedback_decision_id = str(latest_decision.get("id") or "") or None
        if normalized_qc == "yes":
            feedback_label_value = recommendation_to_feedback_label(str(latest_decision.get("recommendation") or ""))
            feedback_reason = "qc_status_marked_yes"
            feedback_notes = "Auto label captured when auditor marked QC as yes."
        else:
            feedback_label_value = "manual_review"
            feedback_reason = "qc_status_marked_no"
            feedback_notes = "Auto label captured when auditor marked QC as no."

        if feedback_label_value:
            try:
                upsert_feedback_label(
                    db=db,
                    claim_id=str(claim_id),
                    decision_id=feedback_decision_id,
                    label_type=AUDITOR_QC_LABEL_TYPE,
                    label_value=feedback_label_value,
                    override_reason=feedback_reason,
                    notes=feedback_notes,
                    created_by=actor_username,
                )
            except Exception:
                feedback_label_value = None

    event_payload: dict[str, str] = {"qc_status": normalized_qc}
    if feedback_label_value:
        event_payload["feedback_label"] = feedback_label_value
    if feedback_decision_id:
        event_payload["feedback_decision_id"] = feedback_decision_id

    workflow_events_repo.emit_workflow_event(
        db=db,
        claim_id=claim_id,
        event_type="completed_report_qc_status_updated",
        actor_id=actor_username,
        payload=event_payload,
    )
    db.commit()

    return CompletedReportQcStatusResponse(
        claim_id=str(row.get("claim_id") or claim_id),
        external_claim_id=str(external_claim_id),
        qc_status=str(row.get("qc_status") or normalized_qc),
        updated_at=str(row.get("updated_at") or ""),
    )


__all__ = [
    "CompletedClaimNotFoundError",
    "InvalidQcStatusError",
    "update_completed_report_qc_status",
]

