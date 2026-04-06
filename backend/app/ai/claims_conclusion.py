from __future__ import annotations

import re
from typing import Any

from app.ai.openai_chat import OpenAIChatError, chat_completions, extract_message_text
from app.core.config import settings
from app.domain.claims.report_conclusion import (
    extract_rule_code_from_entry,
    is_checklist_rule_source,
    strip_html_to_readable_text,
)


_ALLOWED_CONCLUSION_ENDINGS = {
    "Therefore, the claim is admissible.",
    "Therefore, the claim is recommended for rejection.",
    "Therefore, the claim is kept under query.",
}


def _verdict_sentence_from_recommendation(recommendation: str) -> str:
    rec = str(recommendation or "").strip().lower()
    if rec in {"approve", "approved", "admissible", "payable"}:
        return "Therefore, the claim is admissible."
    if rec in {"reject", "rejected", "inadmissible"}:
        return "Therefore, the claim is recommended for rejection."
    return "Therefore, the claim is kept under query."


def _normalize_ai_conclusion_paragraph(value: str, recommendation: str) -> str:
    text_value = str(value or "").strip()
    if not text_value:
        return ""
    text_value = re.sub(r"^```(?:text|markdown)?\s*", "", text_value, flags=re.I)
    text_value = re.sub(r"\s*```$", "", text_value).strip()
    text_value = re.sub(r"<[^>]+>", " ", text_value)
    text_value = re.sub(r"\s+", " ", text_value).strip()
    text_value = text_value.strip('"\'` ')

    for ending in _ALLOWED_CONCLUSION_ENDINGS:
        if text_value.endswith(ending):
            return text_value

    verdict = _verdict_sentence_from_recommendation(recommendation)
    text_value = text_value.rstrip(" .") + ". " + verdict
    return re.sub(r"\s+", " ", text_value).strip()


def _candidate_models() -> list[str]:
    candidates: list[str] = []
    for item in [settings.openai_rag_model, settings.openai_model, "gpt-4.1-mini", "gpt-4o-mini"]:
        model = str(item or "").strip()
        if model and model not in candidates:
            candidates.append(model)
    return candidates


def generate_ai_medico_legal_conclusion(report_html: str, checklist_payload: dict[str, Any], recommendation: str) -> str:
    report_text = strip_html_to_readable_text(report_html)
    if not report_text:
        raise RuntimeError("report text is empty")
    if len(report_text) > 50000:
        report_text = report_text[:50000]

    checklist_rows = checklist_payload.get("checklist") if isinstance(checklist_payload.get("checklist"), list) else []
    triggered_codes: list[str] = []
    seen_codes: set[str] = set()
    for entry in checklist_rows:
        if not isinstance(entry, dict):
            continue
        if not bool(entry.get("triggered")):
            continue
        if not is_checklist_rule_source(str(entry.get("source") or "")):
            continue
        code = extract_rule_code_from_entry(entry)
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        triggered_codes.append(code)

    trigger_hint = ", ".join(triggered_codes) if triggered_codes else "No explicit triggered rule code in latest checklist payload"

    rules_text = (
        "R001 - Meropenem/high-end antibiotic without sepsis markers\n"
        "R002 - ORIF billed without displaced/unstable fracture indication\n"
        "R003 - Pneumonia imaging negative + no culture + high-end antibiotic\n"
        "R004 - UTI without urine culture/sensitivity correlation\n"
        "R005 - Sepsis diagnosis must have markers and culture/work-up\n"
        "R006 - High-end antibiotic not supported by vitals/objective evidence\n"
        "R007 - Ayurvedic hospital accreditation/registration missing\n"
        "R008 - Alcoholism history with CLD context\n"
        "R009 - Hairline fracture in surgical fixation claim\n"
        "R010 - Stable/undisplaced fracture without ORIF/K-wire indication\n"
        "R011 - Fracture case missing X-ray evidence and billing support\n"
        "R013 - UTI + Meropenem supported by culture sensitivity evidence\n"
        "R014 - Low bill but admission justified override\n"
        "R015 - Maternity/LSCS/neonatal override\n"
        "R016 - Sepsis requires combined evidence of vitals, markers, and culture"
    )

    user_prompt = (
        "You are a senior medical claim investigator and audit specialist with expertise in insurance claim adjudication, clinical documentation review, medical necessity assessment, and medico-legal audit writing.\n\n"
        "Your task is to review the Health Claim Investigation Report provided below and generate a single professional conclusion paragraph suitable for TPA/insurance audit use.\n\n"
        "REVIEW OBJECTIVES:\n"
        "1. Examine the full report clinically, logically, and documentarily.\n"
        "2. Apply all relevant rules from R001 to R016.\n"
        "3. Determine whether diagnosis, investigations, treatment, admission, and billing are mutually consistent.\n"
        "4. Identify contradictions, unsupported treatment, missing evidence, weak justification, or incorrect reasoning.\n"
        "5. Assess whether the existing report conclusion is supported by available records.\n"
        "6. Produce a final medico-legal conclusion in one paragraph only.\n"
        "7. For rejection/query outcomes, clearly include the culprit medicine(s) and investigation basis for rejection.\n\n"
        "RULES TO BE APPLIED:\n"
        + rules_text
        + "\n\nSTRICT INSTRUCTIONS:\n"
        "1. Apply every relevant rule; multiple rules may be triggered.\n"
        "2. Do not mention internal category labels.\n"
        "3. Cross-check diagnosis vs findings/investigations, treatment vs severity, antibiotic/procedure support, LOS necessity, and billing intensity.\n"
        "4. If report conclusion is unsupported, explicitly state it is not consistent with available records.\n"
        "5. Maintain formal, objective, concise medico-legal language.\n"
        "6. No bullets, headings, or labels in output.\n"
        "7. Output must be exactly one paragraph.\n"
        "8. Last sentence must be exactly one of: Therefore, the claim is admissible. OR Therefore, the claim is recommended for rejection. OR Therefore, the claim is kept under query.\n"
        "9. If recommendation is rejection or query, explicitly name the culprit medicine(s) (for example Meropenem/high-end antibiotic when applicable) and state the investigation basis (missing/contradictory labs, cultures, imaging, vitals, or other objective findings) in the same paragraph.\n"
        "10. Keep the conclusion detailed but still a single paragraph with no extra sections.\n\n"
        "TRIGGERED RULE HINTS FROM ENGINE: "
        + trigger_hint
        + "\n\nHEALTH CLAIM INVESTIGATION REPORT:\n"
        + report_text
    )

    errors: list[str] = []
    for model in _candidate_models():
        try:
            body = chat_completions(
                [
                    {"role": "system", "content": "You are a medico-legal claim audit writer. Return exactly one paragraph only."},
                    {"role": "user", "content": user_prompt},
                ],
                model=model,
                temperature=0.1,
                timeout_s=120.0,
            )
            raw = extract_message_text(body)
            normalized = _normalize_ai_conclusion_paragraph(raw, recommendation)
            if normalized:
                return normalized
            errors.append(f"{model}: empty_output")
        except OpenAIChatError as exc:
            errors.append(f"{model}: {exc}")
        except Exception as exc:
            errors.append(f"{model}: {exc}")

    raise RuntimeError(f"ai conclusion generation failed: {errors[:3] or ['unknown']}")

