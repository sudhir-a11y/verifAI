from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.dependencies.access_control import doctor_matches_assignment
from app.repositories import claims_repo, decision_results_repo, report_versions_repo
from app.schemas.auth import UserRole
from app.schemas.qc_tools import CompletedReportLatestHtmlResponse


class InvalidSourceError(ValueError):
    pass


class ClaimNotFoundError(RuntimeError):
    pass


class ForbiddenError(RuntimeError):
    pass


class ReportNotFoundError(RuntimeError):
    pass


def _fetch_latest_html_row(db: Session, *, claim_id: UUID, source: str) -> dict | None:
    row = report_versions_repo.get_latest_report_html_for_claim(db, claim_id=claim_id, source=source)
    report_html = str(row.get("report_html") or "") if isinstance(row, dict) else ""
    if row is None or not report_html.strip():
        row = decision_results_repo.get_latest_decision_report_html_for_claim(db, claim_id=claim_id, source=source)
        report_html = str(row.get("report_html") or "") if isinstance(row, dict) else ""
    if row is None or not report_html.strip():
        return None
    return row


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

    claim_row = claims_repo.get_claim_by_id(db, claim_id)
    if claim_row is None:
        raise ClaimNotFoundError("claim not found")

    assigned_doctor_id = claim_row.get("assigned_doctor_id")
    if current_user_role == UserRole.doctor and not doctor_matches_assignment(
        str(assigned_doctor_id or ""),
        current_username,
    ):
        raise ForbiddenError("doctor can access only assigned claims")

    row = _fetch_latest_html_row(db, claim_id=claim_id, source=normalized_source)

    # UX: for doctor UI, if a doctor-authored report isn't present yet, fall back
    # to the latest system report, then any report, so the timeline can render.
    if row is None and normalized_source == "doctor":
        row = _fetch_latest_html_row(db, claim_id=claim_id, source="system")
    if row is None and normalized_source == "doctor":
        row = _fetch_latest_html_row(db, claim_id=claim_id, source="any")

    if row is None:
        # UX: treat "no report yet" as a valid empty response so the UI can
        # render an editable canvas without spamming 404s.
        external_claim_id = str(claim_row.get("external_claim_id") or "")
        report_source = normalized_source if normalized_source in {"doctor", "system"} else "doctor"
        return CompletedReportLatestHtmlResponse(
            claim_id=str(claim_id),
            external_claim_id=external_claim_id,
            version_no=0,
            report_html="",
            report_status="draft",
            report_source=report_source,
            created_by="",
            created_at="",
        )

    return CompletedReportLatestHtmlResponse(
        claim_id=str(row.get("claim_id") or claim_id),
        external_claim_id=str(row.get("external_claim_id") or ""),
        version_no=int(row.get("version_no") or 0),
        report_html=str(row.get("report_html") or ""),
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
