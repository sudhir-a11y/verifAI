from __future__ import annotations

import json
import re
from typing import Any

from app.ai.openai_chat import OpenAIChatError, chat_completions, extract_message_text
from app.core.config import settings


class AIReportGeneratorError(RuntimeError):
    pass


def _parse_json_dict_from_text(raw_text: str) -> dict[str, Any] | None:
    text_value = str(raw_text or "").strip()
    if not text_value:
        return None

    if text_value.startswith("```"):
        text_value = re.sub(r"^```(?:json)?\s*", "", text_value, flags=re.I)
        text_value = re.sub(r"\s*```$", "", text_value)
        text_value = text_value.strip()

    try:
        parsed = json.loads(text_value)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    first = text_value.find("{")
    last = text_value.rfind("}")
    if first >= 0 and last > first:
        candidate = text_value[first : last + 1]
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _strip_scripts(html_value: str) -> str:
    text = str(html_value or "")
    text = re.sub(r"<script\b[^>]*>.*?</script>", "", text, flags=re.I | re.S)
    text = re.sub(r"\son\w+\s*=\s*\"[^\"]*\"", "", text, flags=re.I)
    text = re.sub(r"\son\w+\s*=\s*'[^']*'", "", text, flags=re.I)
    return text.strip()


def _extract_relevant_entities(entities: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(entities, dict):
        return {}
    keys = [
        "name",
        "patient_name",
        "hospital_name",
        "hospital_address",
        "treating_doctor",
        "doctor_registration_number",
        "admission_date",
        "discharge_date",
        "diagnosis",
        "chief_complaints_at_admission",
        "major_diagnostic_finding",
        "clinical_findings",
        "all_investigation_report_lines",
        "all_investigation_reports_with_values",
        "medicine_used",
        "bill_amount",
        "claim_amount",
        "detailed_conclusion",
        "recommendation",
        "kyc_excluded",
        "kyc_exclusion_reason",
        "text_source",
        "text_preview",
        "document_name",
    ]
    out: dict[str, Any] = {}
    for k in keys:
        if k in entities:
            out[k] = entities.get(k)
    return out


def generate_ai_report_html(
    *,
    claim: dict[str, Any],
    structured_data: dict[str, Any] | None,
    extraction_rows: list[dict[str, Any]] | None,
    checklist_payload: dict[str, Any] | None,
    decision_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Generate an HTML report using OpenAI when configured.

    Returns dict:
      - report_html (str)
      - recommendation (str: approve|reject|query)
      - model (str|None)
      - warnings (list[str])
      - used_ai (bool)
    """
    warnings: list[str] = []
    structured = structured_data if isinstance(structured_data, dict) else {}
    checklist = checklist_payload if isinstance(checklist_payload, dict) else {}
    decision = decision_payload if isinstance(decision_payload, dict) else {}

    extracted_docs: list[dict[str, Any]] = []
    for row in (extraction_rows or [])[:40]:
        if not isinstance(row, dict):
            continue
        entities = row.get("extracted_entities")
        if isinstance(entities, str):
            try:
                entities = json.loads(entities)
            except Exception:
                entities = {}
        extracted_docs.append(
            {
                "document_id": row.get("document_id"),
                "model_name": row.get("model_name"),
                "extraction_version": row.get("extraction_version"),
                "created_at": row.get("created_at"),
                "entities": _extract_relevant_entities(entities if isinstance(entities, dict) else {}),
            }
        )

    # Gather brain outputs (if present)
    final_status = str(decision.get("final_status") or "").strip().lower()
    route_target = str(decision.get("route_target") or "").strip()
    risk_score = decision.get("risk_score")
    conflicts = decision.get("conflicts") if isinstance(decision.get("conflicts"), list) else []
    risk_breakdown = decision.get("risk_breakdown") if isinstance(decision.get("risk_breakdown"), list) else []

    ai_decision = str(checklist.get("ai_decision") or "").strip().lower()
    ai_confidence = checklist.get("ai_confidence")

    # If OpenAI is not configured, return empty so caller can fall back.
    if not settings.openai_api_key:
        raise AIReportGeneratorError("OPENAI_API_KEY not configured")

    model_name = str(settings.openai_model or "gpt-4.1-mini")

    input_payload = {
        "claim": {
            "id": claim.get("id"),
            "external_claim_id": claim.get("external_claim_id"),
            "patient_name": claim.get("patient_name"),
            "status": claim.get("status"),
            "priority": claim.get("priority"),
            "tags": claim.get("tags"),
            "generated_by": claim.get("generated_by"),
        },
        "structured_data": structured,
        "extractions": extracted_docs,
        "checklist": {
            "recommendation": checklist.get("recommendation"),
            "route_target": checklist.get("route_target"),
            "manual_review_required": checklist.get("manual_review_required"),
            "review_priority": checklist.get("review_priority"),
            "ai_decision": ai_decision or None,
            "ai_confidence": ai_confidence,
            "explanation_summary": checklist.get("explanation_summary"),
            "source_summary": checklist.get("source_summary"),
        },
        "brain": {
            "final_status": final_status or None,
            "route_target": route_target or None,
            "risk_score": risk_score,
            "risk_breakdown": risk_breakdown,
            "conflicts": conflicts,
        },
    }

    user_prompt = (
        "You are a medico-legal claim report generator for health insurance claims.\n\n"
        "TASK:\n"
        "- Use the provided extracted entities + structured data + checklist + brain outputs.\n"
        "- Generate a filled HTML report (single page) that doctor/auditor can edit.\n"
        "- Write clear medico-legal reasoning, highlight inconsistencies, list missing docs, and conclude with a recommendation.\n\n"
        "STRICT OUTPUT: Return JSON only with keys:\n"
        '{ "report_html": "<!doctype html>...", "recommendation": "approve|reject|query", "summary": "..." }\n\n'
        "HTML rules:\n"
        "- Must be valid HTML (start with <!doctype html>).\n"
        "- No <script> tags, no external assets.\n"
        "- Use simple inline CSS if needed.\n"
        "- Header must always include title exactly: HEALTH CLAIM / Assessment Sheet.\n"
        "- Header must always include company exactly: Medi Assist Insurance TPA Pvt. Ltd.\n"
        "- Header must include generated line with current timestamp and doctor/user name.\n"
        "- Claim Type default: Reimbursement when not explicitly present.\n"
        "- Include sections: Claim Information, Timeline, Diagnosis, Treatment, Investigations, Billing, AI+ML Decision Summary, Medico-legal Reasoning, Final Conclusion.\n"
        "- Keep table labels stable and clean (no OCR garbage keys).\n\n"
        "Recommendation rules:\n"
        "- If GST/registry mismatches or missing critical evidence -> prefer query.\n"
        "- If strong clinical support and no major conflicts -> approve.\n"
        "- If strong fraud/invalid verification and conflicts -> reject or query with reasons.\n\n"
        "Input JSON:\n"
        + json.dumps(input_payload, ensure_ascii=False)[:120000]
    )

    try:
        body = chat_completions(
            [
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": user_prompt},
            ],
            model=model_name,
            temperature=0.1,
            timeout_s=180.0,
            extra={"response_format": {"type": "json_object"}},
        )
        used_model = str(body.get("model") or model_name)
        raw = extract_message_text(body)
        parsed = _parse_json_dict_from_text(raw)
        if not isinstance(parsed, dict):
            raise AIReportGeneratorError("invalid AI response JSON")
        report_html = _strip_scripts(str(parsed.get("report_html") or "").strip())
        if not report_html or "<!doctype html" not in report_html.lower():
            raise AIReportGeneratorError("AI report_html missing or invalid")
        recommendation = str(parsed.get("recommendation") or "").strip().lower()
        if recommendation not in {"approve", "reject", "query"}:
            recommendation = "query"
            warnings.append("ai_recommendation_invalid_defaulted_to_query")
        return {
            "report_html": report_html,
            "recommendation": recommendation,
            "model": used_model,
            "warnings": warnings,
            "used_ai": True,
            "summary": str(parsed.get("summary") or "").strip()[:2000] or None,
        }
    except OpenAIChatError as exc:
        raise AIReportGeneratorError(f"OpenAI error: {exc}") from exc
