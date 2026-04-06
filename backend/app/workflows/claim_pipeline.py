from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.claims_conclusion import generate_ai_medico_legal_conclusion
from app.domain.checklist.checklist_use_cases import evaluate_claim_checklist
from app.domain.claims.events import try_record_workflow_event
from app.domain.claims.report_conclusion import build_rule_based_conclusion_from_report
from app.domain.documents.documents_use_cases import list_documents
from app.domain.extractions.use_cases import run_document_extraction
from app.repositories import report_versions_repo
from app.schemas.extraction import ExtractionProvider


@dataclass(frozen=True)
class ClaimPipelineResult:
    claim_id: UUID
    extracted_documents: int
    checklist_ran: bool
    checklist_result: Any | None
    conclusion_generated: bool
    conclusion: str | None
    conclusion_source: str | None
    conclusion_triggered_rules_count: int | None
    report_version_no: int | None


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
) -> ClaimPipelineResult:
    extracted = 0
    checklist_result: Any | None = None
    conclusion_text: str | None = None
    conclusion_source: str | None = None
    triggered_count: int | None = None
    report_version_no: int | None = None

    if extraction_provider is not None:
        docs = list_documents(db, claim_id, limit=500, offset=0)
        doc_items = getattr(docs, "items", None) or []
        for doc in doc_items:
            doc_id = getattr(doc, "id", None)
            if doc_id is None:
                continue
            run_document_extraction(
                db,
                document_id=doc_id,
                provider=extraction_provider,
                actor_id=actor_id,
                force_refresh=bool(force_extraction_refresh),
            )
            extracted += 1

    checklist_result = evaluate_claim_checklist(
        db,
        claim_id=claim_id,
        actor_id=actor_id,
        force_source_refresh=bool(force_checklist_source_refresh),
    )

    if generate_conclusion:
        latest_report = report_versions_repo.get_latest_report_html_for_claim(db, claim_id=claim_id, source="any")
        if latest_report and str(latest_report.get("report_html") or "").strip():
            report_version_no = int(latest_report.get("version_no") or 0) or None
            report_html = str(latest_report.get("report_html") or "")
            checklist_payload = (
                checklist_result.model_dump()
                if hasattr(checklist_result, "model_dump")
                else (dict(checklist_result) if isinstance(checklist_result, dict) else {})
            )
            recommendation_raw = str(checklist_payload.get("recommendation") or "").strip()

            conclusion_text, rules_triggered = build_rule_based_conclusion_from_report(report_html, checklist_payload)
            triggered_count = int(rules_triggered)
            conclusion_source = "rule_engine"

            if use_ai_conclusion:
                try:
                    ai_text = generate_ai_medico_legal_conclusion(report_html, checklist_payload, recommendation_raw)
                    if ai_text:
                        conclusion_text = ai_text
                        conclusion_source = "ai_medico_legal"
                except Exception:
                    conclusion_source = "rule_engine"

            try_record_workflow_event(
                db,
                claim_id=claim_id,
                actor_id=actor_id,
                event_type="pipeline_conclusion_generated",
                payload={
                    "report_version_no": report_version_no,
                    "triggered_rules_count": int(triggered_count),
                    "use_ai": bool(use_ai_conclusion),
                    "source": str(conclusion_source or ""),
                },
            )

    return ClaimPipelineResult(
        claim_id=claim_id,
        extracted_documents=int(extracted),
        checklist_ran=True,
        checklist_result=checklist_result,
        conclusion_generated=bool(generate_conclusion and bool(conclusion_text)),
        conclusion=conclusion_text,
        conclusion_source=conclusion_source,
        conclusion_triggered_rules_count=triggered_count,
        report_version_no=report_version_no,
    )
