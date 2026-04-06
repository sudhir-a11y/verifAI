from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.claims.report_conclusion import (
    extract_auditor_learning_from_report_html,
    extract_feedback_label_from_report_html,
    feedback_label_from_decision_recommendation,
)
from app.repositories import (
    decision_results_repo,
    feedback_labels_repo,
    report_versions_repo,
    workflow_events_repo,
)
from app.schemas.claim import ClaimReportSaveResponse


def save_claim_report_html(
    db: Session,
    *,
    claim_id: UUID,
    report_html: str,
    report_status: str,
    report_source: str,
    actor_id: str,
    report_created_by: str,
    label_created_by: str,
    is_auditor: bool,
) -> ClaimReportSaveResponse:
    decision_row = decision_results_repo.get_latest_decision_for_claim(db, claim_id)
    decision_id = decision_row.get("id") if decision_row else None
    decision_recommendation = str(decision_row.get("recommendation") or "") if decision_row else ""
    decision_id_uuid: UUID | None = None
    if decision_id:
        decision_id_uuid = UUID(str(decision_id))

    version_no = report_versions_repo.next_version_no(db, claim_id)

    row = report_versions_repo.insert_report_version(
        db,
        claim_id=claim_id,
        decision_id=decision_id_uuid,
        version_no=version_no,
        report_status=report_status,
        report_markdown=report_html,
        created_by=report_created_by,
    )

    workflow_events_repo.emit_workflow_event(
        db=db,
        claim_id=claim_id,
        event_type="report_saved_html",
        actor_id=actor_id,
        payload={"version_no": version_no, "report_status": report_status, "report_source": report_source},
    )

    feedback_label_value = extract_feedback_label_from_report_html(report_html)
    if not feedback_label_value:
        feedback_label_value = feedback_label_from_decision_recommendation(decision_recommendation)

    report_version_decision_id = row.get("decision_id")
    report_version_decision_uuid: UUID | None = None
    if report_version_decision_id:
        report_version_decision_uuid = UUID(str(report_version_decision_id))

    if report_source == "doctor" and feedback_label_value:
        feedback_labels_repo.delete_feedback_labels(db, claim_id=claim_id, label_type="doctor_report_outcome")
        feedback_labels_repo.insert_feedback_label(
            db,
            claim_id=claim_id,
            decision_id=report_version_decision_uuid,
            label_type="doctor_report_outcome",
            label_value=feedback_label_value,
            override_reason="doctor_report_saved_html",
            notes=f"Auto label from doctor report HTML (version {version_no}, status={report_status}).",
            created_by=label_created_by,
        )

    if is_auditor and report_source == "doctor":
        auditor_learning = extract_auditor_learning_from_report_html(report_html)
        feedback_labels_repo.delete_feedback_labels(db, claim_id=claim_id, label_type="auditor_report_learning")
        if auditor_learning:
            auditor_learning_label = (
                feedback_label_value
                or feedback_label_from_decision_recommendation(decision_recommendation)
                or "manual_review"
            )
            feedback_labels_repo.insert_feedback_label(
                db,
                claim_id=claim_id,
                decision_id=report_version_decision_uuid,
                label_type="auditor_report_learning",
                label_value=auditor_learning_label,
                override_reason="auditor_report_saved_html",
                notes=auditor_learning,
                created_by=label_created_by,
            )

    db.commit()

    return ClaimReportSaveResponse(
        id=UUID(str(row["id"])),
        claim_id=UUID(str(row["claim_id"])),
        decision_id=UUID(str(row.get("decision_id"))) if row.get("decision_id") else None,
        version_no=int(row["version_no"]),
        report_status=str(row["report_status"]),
        report_source=report_source,
        created_by=str(row["created_by"]),
        created_at=row["created_at"],
        html_size=len(report_html),
    )
