from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.claims_conclusion import generate_ai_medico_legal_conclusion
from app.domain.claims.events import try_record_workflow_event
from app.domain.claims.report_conclusion import build_rule_based_conclusion_from_report
from app.repositories import report_versions_repo


def generate_conclusion_from_latest_report(
    db: Session,
    *,
    claim_id: UUID,
    actor_id: str,
    checklist_payload: dict[str, Any],
    use_ai_conclusion: bool = False,
) -> tuple[str | None, str | None, int | None, int | None]:
    latest_report = report_versions_repo.get_latest_report_html_for_claim(db, claim_id=claim_id, source="any")
    if not latest_report or not str(latest_report.get("report_html") or "").strip():
        return None, None, None, None

    report_version_no = int(latest_report.get("version_no") or 0) or None
    report_html = str(latest_report.get("report_html") or "")
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

    return conclusion_text, conclusion_source, triggered_count, report_version_no

