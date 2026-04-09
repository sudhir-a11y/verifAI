from __future__ import annotations

import html
import json
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.claims.reports_use_cases import save_claim_report_html
from app.domain.claims.use_cases import get_claim
from app.repositories import claim_structured_data_repo, checklist_context_repo, decision_results_repo
from app.ai.report_generator import AIReportGeneratorError, generate_ai_report_html


def _safe_text(value: Any, max_len: int = 2000) -> str:
    """Safely convert any value to plain text, truncating if too long."""
    if value is None:
        return ""
    t = str(value).strip()
    if t.lower() in {"na", "n/a", "none", "nil", "-", "--", "---", "unknown", "not available"}:
        return ""
    if len(t) > max_len:
        t = t[: max_len - 3] + "..."
    return t


def _render_medicines_html(medicine_used: str) -> str:
    """Render medicine list as an HTML unordered list."""
    raw = _safe_text(medicine_used)
    if not raw:
        return ""
    # Split on newlines and semicolons (not commas — medicine names may contain them)
    parts = [p.strip() for p in re.split(r"[\n;]+", raw) if p.strip()]
    if not parts:
        return ""
    items = "".join(f"<li>{html.escape(p)}</li>" for p in parts)
    return f"<ul>{items}</ul>"


def _render_system_report_html(
    *,
    external_claim_id: str,
    patient_name: str,
    recommendation: str,
    conclusion: str,
    checklist_entries: list[dict[str, Any]],
    structured_data: dict[str, Any] | None = None,
    actor_name: str | None = None,
    checklist_payload: dict[str, Any] | None = None,
    decision_payload: dict[str, Any] | None = None,
) -> str:
    def esc(v: Any) -> str:
        return html.escape(str(v or ""), quote=True)

    sd = structured_data or {}
    checklist = checklist_payload or {}
    decision = decision_payload or {}
    diagnosis = _safe_text(sd.get("diagnosis"))
    hospital = _safe_text(sd.get("hospital_name") or sd.get("hospital"))
    treating_doctor = _safe_text(sd.get("treating_doctor") or sd.get("doctor_name"))
    claim_type = _safe_text(sd.get("claim_type")).lower()
    if claim_type in {"", "-", "unknown"}:
        claim_type = "reimbursement"
    doa = _safe_text(sd.get("doa"))
    dod = _safe_text(sd.get("dod"))
    claim_amount = _safe_text(sd.get("claim_amount"))
    findings = _safe_text(sd.get("findings"), max_len=1000)
    investigations = _safe_text(sd.get("investigation_finding_in_details"), max_len=1000)
    deranged = _safe_text(sd.get("deranged_investigation"), max_len=1000)
    complaints = _safe_text(sd.get("complaints"), max_len=600)
    medicines_html = _render_medicines_html(sd.get("medicine_used", ""))
    high_end_medicine = _safe_text(sd.get("high_end_antibiotic_for_rejection"))
    ai_decision = _safe_text(checklist.get("ai_decision") or checklist.get("recommendation"))
    ai_confidence = checklist.get("ai_confidence") if checklist.get("ai_confidence") is not None else checklist.get("confidence")
    final_status = _safe_text(decision.get("final_status"))
    risk_score = decision.get("risk_score")
    ml_prediction = decision.get("ml_prediction") if isinstance(decision.get("ml_prediction"), dict) else {}
    ml_label = _safe_text(ml_prediction.get("label"))
    ml_confidence = ml_prediction.get("confidence")

    def _row(label: str, value_html: str) -> str:
        if not value_html:
            return ""
        return (
            "<tr>"
            f'<th style="width:32%;text-align:left;background:#e9eef5;border:1px solid #c0c8d6;'
            f'padding:8px 10px;font-size:13px;font-weight:700;">{esc(label)}</th>'
            f'<td style="border:1px solid #c0c8d6;padding:8px 10px;font-size:13px;">'
            f"{value_html}</td>"
            "</tr>"
        )

    # Build structured data table rows
    data_rows = ""
    data_rows += _row("DIAGNOSIS", esc(diagnosis)) if diagnosis else ""
    data_rows += _row("CLAIM TYPE", esc(claim_type.title())) if claim_type else ""
    data_rows += _row("HOSPITAL", esc(hospital)) if hospital else ""
    data_rows += _row("TREATING DOCTOR", esc(treating_doctor)) if treating_doctor else ""
    data_rows += _row("ADMISSION DATE", esc(doa)) if doa else ""
    data_rows += _row("DISCHARGE DATE", esc(dod)) if dod else ""
    data_rows += _row("CHIEF COMPLAINTS", esc(complaints)) if complaints else ""
    data_rows += _row("MAJOR DIAGNOSTIC FINDINGS", esc(findings)) if findings else ""
    data_rows += _row("ALL INVESTIGATION REPORTS", esc(investigations)) if investigations else ""
    data_rows += _row("DERANGED INVESTIGATIONS", esc(deranged)) if deranged else ""
    if medicines_html:
        data_rows += (
            "<tr>"
            '<th style="width:32%;text-align:left;background:#e9eef5;border:1px solid #c0c8d6;'
            'padding:8px 10px;font-size:13px;font-weight:700;">MEDICINES USED</th>'
            f'<td style="border:1px solid #c0c8d6;padding:8px 10px;font-size:13px;">'
            f"{medicines_html}</td>"
            "</tr>"
        )
    data_rows += _row("HIGH-END MEDICINE SIGNAL", esc(high_end_medicine)) if high_end_medicine else ""
    data_rows += _row("CLAIM AMOUNT", esc(claim_amount)) if claim_amount else ""

    triggered = [e for e in checklist_entries if bool(e.get("triggered"))]
    triggered_items = ""
    for entry in triggered[:200]:
        code = esc(entry.get("code") or "")
        name = esc(entry.get("name") or "")
        severity = esc(entry.get("severity") or "")
        decision = esc(entry.get("decision") or "")
        note = esc(entry.get("note") or "")
        missing = entry.get("missing_evidence") if isinstance(entry.get("missing_evidence"), list) else []
        missing_text = esc("; ".join([str(x) for x in missing[:12] if str(x).strip()]))
        triggered_items += (
            "<li>"
            f"<b>{code}</b> — {name} "
            f"(<i>{severity}</i>, <i>{decision}</i>)"
            + (f"<br/>{note}" if note else "")
            + (f"<br/><b>Missing:</b> {missing_text}" if missing_text else "")
            + "</li>"
        )

    structured_table_html = f"<table style='width:100%;border-collapse:collapse;'>{data_rows}</table>" if data_rows else ""

    generated_by = _safe_text(actor_name) or "Doctor"
    generated_line = f"Generated: {esc(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))} | Doctor: {esc(generated_by)}"

    ai_rows = ""
    ai_rows += _row("CHECKLIST RECOMMENDATION", esc(recommendation.upper())) if recommendation else ""
    ai_rows += _row("AI DECISION", esc(ai_decision.upper())) if ai_decision else ""
    ai_rows += _row("AI CONFIDENCE", esc(ai_confidence)) if ai_confidence is not None else ""
    ai_rows += _row("FINAL STATUS", esc(final_status.upper())) if final_status else ""
    ai_rows += _row("RISK SCORE", esc(risk_score)) if risk_score is not None else ""
    ai_rows += _row("ML LABEL", esc(ml_label.upper())) if ml_label else ""
    ai_rows += _row("ML CONFIDENCE", esc(ml_confidence)) if ml_confidence is not None else ""
    ai_table_html = f"<table style='width:100%;border-collapse:collapse;'>{ai_rows}</table>" if ai_rows else ""

    return f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <title>Health Claim Assessment Sheet</title>
    <style>
      body {{ font-family: Arial, sans-serif; line-height: 1.45; padding: 24px; color: #1b2430; }}
      h1 {{ margin: 0; font-size: 26px; }}
      h1 span {{ display:block; font-size:18px; font-weight:600; margin-top:2px; }}
      h2 {{ margin-top: 22px; }}
      .meta {{ color: #444; margin-bottom: 18px; }}
      .box {{ border: 1px solid #cfd7e6; padding: 12px 14px; border-radius: 8px; background: #f8fbff; }}
      .header-box {{ border:1px solid #c0c8d6; border-radius:8px; padding: 14px; background:#f4f7fc; margin-bottom:16px; }}
      .company {{ font-weight:700; margin-top:8px; }}
      ul {{ margin: 8px 0 0 18px; }}
      li {{ margin: 8px 0; }}
    </style>
  </head>
  <body>
    <div class="header-box">
      <h1>HEALTH CLAIM <span>Assessment Sheet</span></h1>
      <div class="meta">{generated_line}</div>
      <div class="company">Medi Assist Insurance TPA Pvt. Ltd.</div>
    </div>

    <h2>Claim Information</h2>
    <div class="meta">
      <div><b>External Claim ID:</b> {esc(external_claim_id)}</div>
      <div><b>Patient:</b> {esc(patient_name)}</div>
    </div>

    {structured_table_html}

    <h2>AI / ML Decision Summary</h2>
    {ai_table_html or "<div class='box'>Decision signals not available.</div>"}

    <h2>Recommendation</h2>
    <div class="box">{esc(recommendation)}</div>

    <h2>Conclusion</h2>
    <div class="box">{esc(conclusion)}</div>

    <h2>Triggered Rules</h2>
    <ul>{triggered_items or "<li>No triggered rules</li>"}</ul>
  </body>
</html>
""".strip()


def save_system_claim_report(
    db: Session,
    *,
    claim_id: UUID,
    actor_id: str,
    checklist_payload: dict[str, Any],
    conclusion_text: str | None,
    report_status: str,
) -> int:
    claim = get_claim(db, claim_id)
    external_claim_id = str(getattr(claim, "external_claim_id", "") or "")
    patient_name = str(getattr(claim, "patient_name", "") or "")
    recommendation = str(checklist_payload.get("recommendation") or "")
    conclusion = (
        str(conclusion_text or "").strip()
        or str((checklist_payload.get("source_summary") or {}).get("reporting", {}).get("conclusion") or "")
        or str(checklist_payload.get("recommendation_text") or "")
    )
    checklist_entries = checklist_payload.get("checklist") if isinstance(checklist_payload.get("checklist"), list) else []

    # Fetch structured data to enrich the report with medicine, diagnosis, etc.
    structured_data = None
    try:
        structured_data = claim_structured_data_repo.get_structured_data(db, str(claim_id))
    except Exception:
        pass  # Report still renders without structured data

    report_html = ""
    try:
        decision_row = decision_results_repo.get_latest_decision_row_for_claim(db, claim_id)
        decision_payload = decision_row.get("decision_payload") if isinstance(decision_row, dict) else {}
        if isinstance(decision_payload, str):
            decision_payload = json.loads(decision_payload)
        if not isinstance(decision_payload, dict):
            decision_payload = {}

        extraction_rows = checklist_context_repo.list_latest_extractions_per_document(db, claim_id=claim_id)
        ai_out = generate_ai_report_html(
            claim={
                "id": str(claim_id),
                "external_claim_id": external_claim_id,
                "patient_name": patient_name,
                "status": str(getattr(claim, "status", "") or ""),
                "priority": getattr(claim, "priority", None),
                "tags": getattr(claim, "tags", []),
                "generated_by": actor_id,
            },
            structured_data=structured_data if isinstance(structured_data, dict) else {},
            extraction_rows=extraction_rows,
            checklist_payload=checklist_payload,
            decision_payload=decision_payload,
        )
        report_html = str(ai_out.get("report_html") or "").strip()
    except (AIReportGeneratorError, Exception):
        report_html = ""

    if not report_html:
        actor_name = str(actor_id or "").strip()
        if actor_name.startswith("system:"):
            actor_name = actor_name.split("system:", 1)[1] or actor_name
        report_html = _render_system_report_html(
            external_claim_id=external_claim_id,
            patient_name=patient_name,
            recommendation=recommendation,
            conclusion=conclusion,
            checklist_entries=[e for e in checklist_entries if isinstance(e, dict)],
            structured_data=structured_data,
            actor_name=actor_name,
            checklist_payload=checklist_payload,
            decision_payload=decision_payload,
        )

    created_by = actor_id if str(actor_id or "").lower().startswith("system:") else f"system:{actor_id}"
    resp = save_claim_report_html(
        db,
        claim_id=claim_id,
        report_html=report_html,
        report_status=str(report_status or "completed").strip().lower() or "completed",
        report_source="system",
        actor_id=actor_id,
        report_created_by=created_by,
        label_created_by=actor_id,
        is_auditor=False,
    )
    return int(resp.version_no)
