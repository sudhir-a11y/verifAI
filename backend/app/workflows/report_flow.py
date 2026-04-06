from __future__ import annotations

import html
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.claims.reports_use_cases import save_claim_report_html
from app.domain.claims.use_cases import get_claim


def _render_system_report_html(
    *,
    external_claim_id: str,
    patient_name: str,
    recommendation: str,
    conclusion: str,
    checklist_entries: list[dict[str, Any]],
) -> str:
    def esc(v: Any) -> str:
        return html.escape(str(v or ""), quote=True)

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

    return f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <title>Claim Report</title>
    <style>
      body {{ font-family: Arial, sans-serif; line-height: 1.45; padding: 24px; }}
      h1 {{ margin: 0 0 8px; }}
      h2 {{ margin-top: 22px; }}
      .meta {{ color: #444; margin-bottom: 18px; }}
      .box {{ border: 1px solid #ddd; padding: 12px 14px; border-radius: 8px; background: #fafafa; }}
      ul {{ margin: 8px 0 0 18px; }}
      li {{ margin: 8px 0; }}
    </style>
  </head>
  <body>
    <h1>verifAI — System Claim Report</h1>
    <div class="meta">
      <div><b>External Claim ID:</b> {esc(external_claim_id)}</div>
      <div><b>Patient:</b> {esc(patient_name)}</div>
    </div>

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

    report_html = _render_system_report_html(
        external_claim_id=external_claim_id,
        patient_name=patient_name,
        recommendation=recommendation,
        conclusion=conclusion,
        checklist_entries=[e for e in checklist_entries if isinstance(e, dict)],
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

