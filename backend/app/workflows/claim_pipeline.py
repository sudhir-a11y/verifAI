from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.workflows.checklist_flow import run_checklist_for_claim
from app.workflows.conclusion_flow import generate_conclusion_from_latest_report
from app.workflows.decision_flow import get_latest_decision_for_claim
from app.workflows.extraction_flow import extract_all_documents_for_claim
from app.workflows.report_flow import save_system_claim_report
from app.repositories import report_versions_repo
from app.schemas.extraction import ExtractionProvider


@dataclass(frozen=True)
class ClaimPipelineResult:
    claim_id: UUID
    extracted_documents: int
    checklist_ran: bool
    checklist_result: Any | None
    latest_decision: dict[str, Any] | None
    conclusion_generated: bool
    conclusion: str | None
    conclusion_source: str | None
    conclusion_triggered_rules_count: int | None
    report_version_no: int | None
    report_saved: bool
    saved_report_version_no: int | None


def run_claim_pipeline(
    db: Session,
    *,
    claim_id: UUID,
    actor_id: str,
    extraction_provider: ExtractionProvider | None = None,
    force_extraction_refresh: bool = False,
    force_checklist_source_refresh: bool = False,
    generate_conclusion: bool = False,
    use_ai_conclusion: bool = False,
    generate_report: bool = False,
    report_status: str = "completed",
) -> ClaimPipelineResult:
    extracted = 0
    checklist_result: Any | None = None
    latest_decision: dict[str, Any] | None = None
    conclusion_text: str | None = None
    conclusion_source: str | None = None
    triggered_count: int | None = None
    report_version_no: int | None = None
    report_saved = False
    saved_report_version_no: int | None = None

    if extraction_provider is not None:
        extracted = extract_all_documents_for_claim(
            db,
            claim_id=claim_id,
            actor_id=actor_id,
            provider=extraction_provider,
            force_refresh=bool(force_extraction_refresh),
        )

    checklist_result = run_checklist_for_claim(
        db,
        claim_id=claim_id,
        actor_id=actor_id,
        force_source_refresh=bool(force_checklist_source_refresh),
    )

    checklist_payload = (
        checklist_result.model_dump() if hasattr(checklist_result, "model_dump") else checklist_result
    )
    checklist_payload = checklist_payload if isinstance(checklist_payload, dict) else {}

    latest_decision = get_latest_decision_for_claim(db, claim_id=claim_id)

    if generate_conclusion:
        (
            conclusion_text,
            conclusion_source,
            triggered_count,
            report_version_no,
        ) = generate_conclusion_from_latest_report(
            db,
            claim_id=claim_id,
            actor_id=actor_id,
            checklist_payload=checklist_payload,
            use_ai_conclusion=bool(use_ai_conclusion),
        )

    if generate_report:
        saved_report_version_no = save_system_claim_report(
            db,
            claim_id=claim_id,
            actor_id=actor_id,
            checklist_payload=checklist_payload,
            conclusion_text=conclusion_text,
            report_status=str(report_status or "completed"),
        )
        report_saved = True

    return ClaimPipelineResult(
        claim_id=claim_id,
        extracted_documents=int(extracted),
        checklist_ran=True,
        checklist_result=checklist_result,
        latest_decision=latest_decision,
        conclusion_generated=bool(generate_conclusion and bool(conclusion_text)),
        conclusion=conclusion_text,
        conclusion_source=conclusion_source,
        conclusion_triggered_rules_count=triggered_count,
        report_version_no=report_version_no,
        report_saved=report_saved,
        saved_report_version_no=saved_report_version_no,
    )
