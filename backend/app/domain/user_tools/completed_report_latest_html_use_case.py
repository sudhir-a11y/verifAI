from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.auth import UserRole
from app.schemas.qc_tools import CompletedReportLatestHtmlResponse
from app.services.access_control import doctor_matches_assignment
from app.repositories import claims_repo, decision_results_repo, report_versions_repo


class InvalidSourceError(ValueError):
    pass


class ClaimNotFoundError(RuntimeError):
    pass


class ForbiddenError(RuntimeError):
    pass


class ReportNotFoundError(RuntimeError):
    pass


def get_completed_report_latest_html(
    db: Session,
    *,
    claim_id: UUID,
    source: str,
    current_user_role: UserRole,
    current_username: str,
) -> CompletedReportLatestHtmlResponse:
    normalized_source = str(source or "any").strip().lower() or "any"
    if normalized_source not in {"any", "doctor", "system"}:
        raise InvalidSourceError("invalid source. allowed: any, doctor, system")

    assigned_doctor_id = claims_repo.get_claim_assigned_doctor_id(db, claim_id=claim_id)
    if assigned_doctor_id is None:
        raise ClaimNotFoundError("claim not found")

    if current_user_role == UserRole.doctor and not doctor_matches_assignment(
        str(assigned_doctor_id or ""),
        current_username,
    ):
        raise ForbiddenError("doctor can access only assigned claims")

    row = report_versions_repo.get_latest_report_html_for_claim(db, claim_id=claim_id, source=normalized_source)
    report_html = str(row.get("report_html") or "") if row is not None else ""
    if row is None or not report_html.strip():
        row = decision_results_repo.get_latest_decision_report_html_for_claim(db, claim_id=claim_id, source=normalized_source)

    if row is None:
        detail = (
            "No saved report HTML found for this claim and source."
            if normalized_source != "any"
            else "No saved report HTML found for this claim."
        )
        raise ReportNotFoundError(detail)

    report_html = str(row.get("report_html") or "")
    if not report_html.strip():
        detail = (
            "No saved report HTML found for this claim and source."
            if normalized_source != "any"
            else "No saved report HTML found for this claim."
        )
        raise ReportNotFoundError(detail)

    return CompletedReportLatestHtmlResponse(
        claim_id=str(row.get("claim_id") or claim_id),
        external_claim_id=str(row.get("external_claim_id") or ""),
        version_no=int(row.get("version_no") or 0),
        report_html=report_html,
        report_status=str(row.get("report_status") or "draft"),
        report_source=str(row.get("report_source") or normalized_source),
        created_by=str(row.get("created_by") or ""),
        created_at=str(row.get("created_at") or ""),
    )


__all__ = [
    "ClaimNotFoundError",
    "ForbiddenError",
    "InvalidSourceError",
    "ReportNotFoundError",
    "get_completed_report_latest_html",
]

