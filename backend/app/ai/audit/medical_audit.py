from __future__ import annotations

import json
import re
import time
from typing import Any

from app.ai.openai_chat import OpenAIChatError, chat_completions, extract_message_text
from app.core.config import settings

OPENAI_MERGED_AUDIT_DISCLAIMER = (
    "This is an AI-assisted review and should be validated by a qualified medical professional."
)
OPENAI_MERGED_RATE_LIMIT_MARKER = "OPENAI_RATE_LIMITED"
OPENAI_MERGED_RATE_LIMIT_COOLDOWN_SECONDS = 300

_openai_merged_rate_limited_until = 0.0


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


def _dedup_text_list(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text_item = str(item or "").strip()
        if not text_item:
            continue
        key = text_item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text_item)
        if len(out) >= max(1, int(limit or 1)):
            break
    return out


def _prepare_claim_text_for_openai(claim_text: str, max_chars: int = 60000) -> str:
    raw = str(claim_text or "").strip()
    if not raw:
        return ""
    lines: list[str] = []
    seen: set[str] = set()
    for line in re.split(r"\r\n|\r|\n", raw):
        t = line.strip()
        if not t:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(t)
    compact = "\n".join(lines).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars]


def run_openai_merged_medical_audit(claim_text: str) -> dict[str, Any]:
    global _openai_merged_rate_limited_until

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    now_ts = time.time()
    if now_ts < _openai_merged_rate_limited_until:
        remaining = int(max(1, _openai_merged_rate_limited_until - now_ts))
        raise RuntimeError(f"{OPENAI_MERGED_RATE_LIMIT_MARKER}: cooldown {remaining}s")

    merged_text = _prepare_claim_text_for_openai(claim_text)
    if not merged_text:
        raise RuntimeError("No extracted claim text available for merged review")

    user_prompt = (
        "You are an expert medical auditor and claim reviewer.\n\n"
        "Your task is to analyze medical documents (including OCR-extracted text, prescriptions, reports, and bills) and determine whether the hospitalization and treatment are justified.\n\n"
        "Follow these strict instructions:\n\n"
        "1. Admission Justification:\n"
        "- Evaluate whether hospital admission was medically necessary.\n"
        '- Classify as: "yes", "no", or "uncertain".\n\n'
        "2. Treatment Evaluation:\n"
        "- Check if medicines and procedures are appropriate for the diagnosis.\n"
        "- Flag unnecessary or excessive treatments.\n\n"
        "3. Diagnosis Validation:\n"
        "- Verify whether investigations/tests support the diagnosis.\n"
        "- Highlight mismatches or missing diagnostic evidence.\n\n"
        "4. Length of Stay (LOS):\n"
        "- Assess whether the duration of hospitalization is justified.\n\n"
        "5. Doctor Validity:\n"
        "- Comment if doctor details suggest mismatch (if available).\n\n"
        "6. Evidence Extraction:\n"
        "- Extract key supporting data:\n"
        "  - Symptoms\n"
        "  - Vitals\n"
        "  - Lab results\n"
        "  - Medicines\n"
        "  - Procedures\n\n"
        "7. Missing Information:\n"
        "- Clearly list any missing documents or data required for proper assessment.\n\n"
        "8. Rules:\n"
        "- DO NOT invent information.\n"
        '- If unclear text exists (OCR issues), mark as "[unclear]".\n'
        "- Be conservative and evidence-based.\n\n"
        "9. Conclusion Style (MANDATORY):\n"
        "- In `rationale`, write a clear medical conclusion in this style:\n"
        '  "<age> year old patient diagnosed with <diagnosis> with chief complaints of <complaints>, having deranged investigation values of <important abnormal values>, and treated with following medicines <medicine list>."\n'
        "- If any part is not available, write [unclear] for that part.\n\n"
        "10. Output Format (STRICT JSON ONLY):\n\n"
        "{\n"
        '  "admission_required": "yes | no | uncertain",\n'
        '  "confidence": 0-100,\n'
        '  "rationale": "One-paragraph conclusion in required format",\n'
        '  "evidence": [\n'
        '    "point 1",\n'
        '    "point 2"\n'
        "  ],\n"
        '  "missing_information": [\n'
        '    "missing item 1"\n'
        "  ],\n"
        f'  "disclaimer": "{OPENAI_MERGED_AUDIT_DISCLAIMER}"\n'
        "}\n\n"
        "Input:\n"
        + merged_text
    )

    configured_model = "gpt-4.1-mini"
    model_candidates: list[str] = [configured_model]

    errors: list[str] = []
    used_model = configured_model
    parsed: dict[str, Any] | None = None
    raw_output = ""

    for candidate in model_candidates:
        try:
            body = chat_completions(
                [
                    {
                        "role": "system",
                        "content": "You are an expert medical auditor and claim reviewer. Return strict JSON only.",
                    },
                    {"role": "user", "content": user_prompt},
                ],
                model=candidate,
                temperature=0.0,
                timeout_s=120.0,
                extra={"response_format": {"type": "json_object"}},
            )
            used_model = str(body.get("model") or candidate)
            raw_output = extract_message_text(body)
            parsed = _parse_json_dict_from_text(raw_output)
            if isinstance(parsed, dict):
                break
            errors.append(f"{candidate} => invalid_json")
        except OpenAIChatError as exc:
            if exc.status_code == 429:
                _openai_merged_rate_limited_until = time.time() + OPENAI_MERGED_RATE_LIMIT_COOLDOWN_SECONDS
                raise RuntimeError(OPENAI_MERGED_RATE_LIMIT_MARKER) from exc
            errors.append(f"{candidate} => HTTP {exc.status_code or 'unknown'}: {exc}")
        except Exception as exc:
            errors.append(f"{candidate} => {exc}")

    if not isinstance(parsed, dict):
        raise RuntimeError(
            "Merged OpenAI medical audit failed. "
            f"models_tried={model_candidates}; errors={errors[:3] or ['none']}"
        )

    admission_required = str(parsed.get("admission_required") or "uncertain").strip().lower()
    if admission_required not in {"yes", "no", "uncertain"}:
        admission_required = "uncertain"

    confidence_raw = parsed.get("confidence")
    confidence = 0.0
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(100.0, max(0.0, confidence))

    rationale = str(parsed.get("rationale") or "").strip()
    evidence = _dedup_text_list(parsed.get("evidence"), limit=30)
    missing_information = _dedup_text_list(parsed.get("missing_information"), limit=30)
    disclaimer = str(parsed.get("disclaimer") or "").strip() or OPENAI_MERGED_AUDIT_DISCLAIMER

    return {
        "admission_required": admission_required,
        "confidence": confidence,
        "rationale": rationale,
        "evidence": evidence,
        "missing_information": missing_information,
        "disclaimer": disclaimer,
        "used_model": used_model,
        "models_tried": model_candidates,
        "errors": errors,
        "raw_output": raw_output,
    }


__all__ = [
    "OPENAI_MERGED_RATE_LIMIT_MARKER",
    "run_openai_merged_medical_audit",
]

