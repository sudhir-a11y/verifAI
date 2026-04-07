from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from app.ai.openai_chat import OpenAIChatError, chat_completions, extract_message_text
from app.core.config import settings


STRUCTURED_FIELDS: tuple[str, ...] = (
    "doctor_name",
    "diagnosis",
    "medicines",
    "duration",
    "hospital",
    "date",
)


class DocumentStructuringError(Exception):
    pass


class DocumentStructuringModelError(DocumentStructuringError):
    pass


def structure_document_text(
    ocr_text: str,
    *,
    use_llm: bool = True,
    model: str | None = None,
) -> dict[str, Any]:
    """Convert OCR text to a small, stable medical JSON structure.

    Output schema:
      - doctor_name: str
      - diagnosis: str
      - medicines: list[str]
      - duration: str
      - hospital: str
      - date: str (ISO yyyy-mm-dd when possible)

    Notes:
      - If OpenAI is configured and ``use_llm`` is true, an LLM attempt is made.
      - If the LLM attempt fails or is not configured, falls back to rule-based parsing.
      - This module must not access the DB.
    """

    cleaned = _normalize_ocr_text(ocr_text)
    if not cleaned:
        return _empty_structured_payload()

    if use_llm and settings.openai_api_key:
        try:
            return _structure_with_llm(cleaned, model=model)
        except Exception:
            # Keep pipeline resilient: fall back to rule-based structuring.
            pass

    return _structure_rule_based(cleaned)


def _empty_structured_payload() -> dict[str, Any]:
    return {
        "doctor_name": "",
        "diagnosis": "",
        "medicines": [],
        "duration": "",
        "hospital": "",
        "date": "",
    }


def _normalize_ocr_text(raw: str) -> str:
    text = str(raw or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_json_dict_from_text(raw_text: str) -> dict[str, Any] | None:
    text_value = str(raw_text or "").strip()
    if not text_value:
        return None

    if text_value.startswith("```"):
        text_value = re.sub(r"^```(?:json)?\s*", "", text_value, flags=re.I)
        text_value = re.sub(r"\s*```$", "", text_value).strip()

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


def _normalize_model_name(raw_model: str | None) -> str:
    configured_model_raw = str(raw_model or "").strip()
    configured_model = configured_model_raw.replace("_", ".") if configured_model_raw else "gpt-4o-mini"
    return configured_model


def _coerce_structured_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return _empty_structured_payload()

    out = _empty_structured_payload()
    for key in STRUCTURED_FIELDS:
        if key not in raw:
            continue
        out[key] = raw[key]

    out["doctor_name"] = _to_clean_text(out.get("doctor_name"))
    out["diagnosis"] = _to_clean_text(out.get("diagnosis"))
    out["duration"] = _to_clean_text(out.get("duration"))
    out["hospital"] = _to_clean_text(out.get("hospital"))
    out["date"] = _normalize_date_string(out.get("date"))

    meds_raw = out.get("medicines")
    if isinstance(meds_raw, list):
        out["medicines"] = [_to_clean_text(x) for x in meds_raw if _to_clean_text(x)]
    elif isinstance(meds_raw, str):
        parts = [p.strip() for p in re.split(r"[\n,;]+", meds_raw) if p.strip()]
        out["medicines"] = parts
    else:
        out["medicines"] = []

    return out


def _to_clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return re.sub(r"\s+", " ", str(value)).strip()


def _normalize_date_string(value: Any) -> str:
    raw = _to_clean_text(value)
    if not raw:
        return ""

    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", raw)
    if m:
        try:
            dt = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.isoformat()
        except Exception:
            return ""

    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", raw)
    if m:
        d, mon, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            dt = date(y, mon, d)
            return dt.isoformat()
        except Exception:
            return ""

    return ""


def _structure_with_llm(text: str, *, model: str | None) -> dict[str, Any]:
    prompt = (
        "You are a medical document structurer. "
        "Given OCR text from a prescription/lab note/invoice, extract ONLY what is present. "
        "Return strict JSON only, with these exact keys:\n"
        "- doctor_name: string\n"
        "- diagnosis: string\n"
        "- medicines: array of strings (each medicine as a short single-line string)\n"
        "- duration: string\n"
        "- hospital: string\n"
        "- date: string (yyyy-mm-dd if present; else empty)\n\n"
        "Rules:\n"
        "- Do not hallucinate; if unknown, use empty string / empty array.\n"
        "- Do not include any extra keys.\n"
        "- Prefer preserving original medicine spellings from OCR.\n\n"
        "OCR TEXT:\n"
        + text
    )

    candidates: list[str] = []
    for candidate in [
        model,
        settings.openai_rag_model,
        settings.openai_model,
        "gpt-4o-mini",
        "gpt-4.1-mini",
    ]:
        normalized = _normalize_model_name(candidate)
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    errors: list[str] = []
    for candidate in candidates:
        try:
            body = chat_completions(
                [
                    {"role": "system", "content": "Return strict JSON only."},
                    {"role": "user", "content": prompt},
                ],
                model=candidate,
                temperature=0.0,
                timeout_s=90.0,
                extra={"response_format": {"type": "json_object"}},
            )
            raw_output = extract_message_text(body)
            parsed = _parse_json_dict_from_text(raw_output)
            if not isinstance(parsed, dict):
                errors.append(f"{candidate}: invalid_json")
                continue
            structured = _coerce_structured_payload(parsed)
            if not isinstance(structured.get("medicines"), list):
                errors.append(f"{candidate}: invalid_medicines")
                continue
            return structured
        except OpenAIChatError as exc:
            errors.append(f"{candidate}: HTTP {exc.status_code or 'unknown'}: {exc}")
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")

    raise DocumentStructuringModelError(f"Document structuring failed. models_tried={candidates}; errors={errors[:3] or ['unknown']}")


_MED_PREFIX_RE = re.compile(
    r"^\s*(?:tab(?:let)?|cap(?:sule)?|syr(?:up)?|syp|inj(?:ection)?|drop(?:s)?|ointment|cream|gel|spray|solution|susp(?:ension)?)\b",
    re.I,
)
_HOSPITAL_RE = re.compile(r"\b(hospital|clinic|medical\s*(?:centre|center)|nursing\s*home)\b", re.I)
_DOCTOR_RE = re.compile(r"^\s*(?:dr\.?|doctor)\s+([A-Za-z][A-Za-z .'\-]{2,})\s*$", re.I)
_DURATION_RE = re.compile(r"\b(\d{1,3})\s*(day|days|week|weeks|month|months)\b", re.I)


def _structure_rule_based(text: str) -> dict[str, Any]:
    out = _empty_structured_payload()
    lines = [_clean_line(line) for line in text.split("\n")]
    lines = [line for line in lines if line]

    if not lines:
        return out

    full_text = "\n".join(lines)

    out["date"] = _normalize_date_string(full_text)

    # Doctor
    for line in lines:
        m = _DOCTOR_RE.match(line)
        if m:
            out["doctor_name"] = _to_clean_text(m.group(1))
            break
        if re.search(r"\bdr\.?\b", line, flags=re.I):
            # fallback for "Dr Sharma, MBBS" style
            m2 = re.search(r"\bdr\.?\s+([A-Za-z][A-Za-z .'\-]{2,})", line, flags=re.I)
            if m2:
                out["doctor_name"] = _to_clean_text(m2.group(1))
                break

    # Hospital
    for line in lines:
        if _HOSPITAL_RE.search(line) and 4 <= len(line) <= 160:
            out["hospital"] = _to_clean_text(line)
            break

    # Duration
    m = _DURATION_RE.search(full_text)
    if m:
        out["duration"] = f"{m.group(1)} {m.group(2).lower()}"

    # Medicines
    medicines: list[str] = []
    for line in lines:
        if _MED_PREFIX_RE.search(line) or re.search(r"\b(?:mg|ml|mcg|iu)\b", line, flags=re.I):
            candidate = _strip_med_prefix(line)
            if candidate and candidate.lower() not in {"dr", "doctor"}:
                medicines.append(candidate)
    out["medicines"] = _dedupe_preserve_order(medicines)

    # Diagnosis (best-effort)
    diagnosis_candidates: list[str] = []
    for line in lines:
        low = line.lower()
        if out["doctor_name"] and out["doctor_name"].lower() in low:
            continue
        if out["hospital"] and out["hospital"].lower() in low:
            continue
        if out["duration"] and out["duration"].lower() in low:
            continue
        if _MED_PREFIX_RE.search(line):
            continue
        if _DURATION_RE.search(line):
            continue
        if _looks_like_date(line):
            continue
        if len(line) < 3 or len(line) > 120:
            continue
        diagnosis_candidates.append(line)

    if diagnosis_candidates:
        # Prefer a shorter, symptom-like line.
        diagnosis_candidates.sort(key=lambda s: (len(s), s))
        out["diagnosis"] = _to_clean_text(diagnosis_candidates[0])

    return out


def _clean_line(line: str) -> str:
    value = re.sub(r"\s+", " ", str(line or "")).strip(" \t-•*.:;")
    return value.strip()


def _strip_med_prefix(line: str) -> str:
    value = _to_clean_text(line)
    if not value:
        return ""
    value = _MED_PREFIX_RE.sub("", value).strip(" :-")
    value = re.sub(r"\s{2,}", " ", value).strip()
    return value


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        norm = re.sub(r"[^a-z0-9]+", "", item.lower())
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(item)
    return out


def _looks_like_date(text: str) -> bool:
    t = _to_clean_text(text)
    if not t:
        return False
    return bool(
        re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
        or re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", t)
    )

