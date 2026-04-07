"""Doctor verification layer — human approval before final decision.

Pipeline:  OCR → structurer → checklist → **doctor_verification** → decision

This module lets a medical reviewer:
  - Accept AI-extracted structured data as-is
  - Override specific fields (diagnosis, medicines, etc.)
  - Add review notes
  - Produce a final, auditable decision record

Usage::

    result = verify_doctor_decision(
        structured=structured_data,
        checklist=checklist_result,
        doctor_id="dr_sharma",
        decision="approve",
        notes="Sepsis suspected — antibiotic justified",
        edited_fields={"diagnosis": "Septicemia secondary to UTI"},
    )
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DoctorVerificationError(Exception):
    """Raised when doctor input is malformed."""


# ---------------------------------------------------------------------------
# Empty structured template
# ---------------------------------------------------------------------------

_EMPTY_STRUCTURED: dict[str, Any] = {
    "doctor_name": "",
    "diagnosis": "",
    "medicines": [],
    "duration": "",
    "hospital": "",
    "date": "",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_doctor_verification(
    structured_data: dict[str, Any],
    checklist: dict[str, Any] | None = None,
    *,
    doctor_decision: str = "query",
    notes: str = "",
    edited_fields: dict[str, Any] | None = None,
    doctor_id: str | None = None,
) -> dict[str, Any]:
    """Convenience wrapper matching the Next Update contract.

    Returns at least:
        {"doctor_decision","notes","edited_fields","confidence"}
    """
    result = verify_doctor_decision(
        structured=structured_data,
        checklist=checklist or {},
        doctor_id=doctor_id,
        decision=doctor_decision,
        notes=notes,
        edited_fields=edited_fields,
    )
    # Contract output (minimal + stable)
    return {
        "doctor_decision": result["doctor_decision"],
        "notes": result["notes"],
        "edited_fields": result["edited_fields"],
        "confidence": result["confidence"],
    }


def verify_doctor_decision(
    structured: dict[str, Any],
    checklist: dict[str, Any] | None,
    *,
    doctor_id: str | None = None,
    decision: str,
    notes: str = "",
    edited_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Process a doctor's review and produce a verified decision record.

    Parameters
    ----------
    structured:
        Original structured output from ``document_structurer``.
    checklist:
        Result from ``checklist_engine.run_checklist()``.
    doctor_id:
        Optional identifier of the reviewing doctor (username/registration id).
    decision:
        ``"approve"``, ``"reject"``, or ``"query"`` (needs more info).
    notes:
        Free-text clinical note explaining the decision.
    edited_fields:
        Dict of fields the doctor corrected, e.g.
        ``{"diagnosis": "Septicemia", "medicines": ["Meropenem 1g IV"]}``.

    Returns
    -------
    dict with keys:
        - ``doctor_decision``: ``"approve"`` | ``"reject"`` | ``"query"``
        - ``notes``: str
        - ``edited_fields``: dict of changes
        - ``verified_data``: structured data with doctor edits applied
        - ``confidence``: float 0.0–1.0
        - ``reviewed_at``: ISO timestamp
        - ``doctor_id``: str | None
        - ``flags_overridden``: bool — whether doctor edited a flagged field
    """

    decision = _normalize_decision(decision)
    notes = _clean_notes(notes)
    edits = _coerce_edited_fields(edited_fields)
    doctor_id_clean = str(doctor_id or "").strip()[:100]
    if not doctor_id_clean:
        raise DoctorVerificationError("doctor_id is required")

    # Ensure structured is always a valid dict
    data = dict(_EMPTY_STRUCTURED)
    if isinstance(structured, dict):
        data.update(structured)

    # Apply doctor edits on top of original structured data
    verified_data = _apply_edits(data, edits)

    # Did the doctor override any checklist flags?
    flags_overridden = _detect_flag_override(checklist or {}, edits)

    # Confidence reflects: did the doctor fix the issues?
    confidence = _compute_verified_confidence(
        data, checklist or {}, edits, decision
    )

    return {
        "doctor_decision": decision,
        "notes": notes,
        "edited_fields": edits,
        "verified_data": verified_data,
        "confidence": round(confidence, 4),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "doctor_id": doctor_id_clean,
        "flags_overridden": flags_overridden,
    }


# ---------------------------------------------------------------------------
# Decision normalization
# ---------------------------------------------------------------------------

_VALID_DECISIONS = {"approve", "reject", "query"}
_DECISION_ALIASES = {
    "approve": "approve",
    "approved": "approve",
    "accept": "approve",
    "accepted": "approve",
    "yes": "approve",
    "ok": "approve",
    "reject": "reject",
    "rejected": "reject",
    "deny": "reject",
    "denied": "reject",
    "no": "reject",
    "query": "query",
    "querying": "query",
    "needs-more-info": "query",
    "needs_more_info": "query",
    "needs more info": "query",
    "pending": "query",
    "review": "query",
}


def _normalize_decision(raw: str) -> str:
    cleaned = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    mapped = _DECISION_ALIASES.get(cleaned)
    if mapped:
        return mapped
    if raw in _VALID_DECISIONS:
        return raw
    raise DoctorVerificationError(
        f"Invalid decision '{raw}'. Must be one of: {_VALID_DECISIONS}"
    )


def normalize_decision(raw: str) -> str:
    """Public wrapper for decision normalization."""
    return _normalize_decision(raw)


# ---------------------------------------------------------------------------
# Field edit application
# ---------------------------------------------------------------------------

_FIELD_ALIASES: dict[str, str] = {
    # Generic/legacy structurer keys
    "doctor_name": "doctor_name",
    "hospital": "hospital",
    "medicines": "medicines",
    "date": "date",
    # Claim structured-data keys
    "treating_doctor": "doctor_name",
    "hospital_name": "hospital",
    "medicine_used": "medicines",
    "doa": "doa",
    "dod": "dod",
    "claim_amount": "claim_amount",
    # Shared
    "diagnosis": "diagnosis",
    "duration": "duration",
}

_EDITABLE_FIELDS = set(_FIELD_ALIASES.keys())


def _canonical_field(key: str) -> str:
    return _FIELD_ALIASES.get(str(key or "").strip(), str(key or "").strip())


def _apply_edits(
    structured: dict[str, Any],
    edits: dict[str, Any],
) -> dict[str, Any]:
    """Return a copy of structured data with doctor edits applied."""
    out = dict(structured)
    for key, value in edits.items():
        if key not in _EDITABLE_FIELDS:
            continue
        # If user edits generic fields, also apply to structured-data equivalents when present.
        # (Example: editing "doctor_name" should update "treating_doctor" if that's the key used.)
        target_keys = {key}
        canon = _canonical_field(key)
        if canon == "doctor_name" and "treating_doctor" in out:
            target_keys.add("treating_doctor")
        if canon == "hospital" and "hospital_name" in out:
            target_keys.add("hospital_name")
        if canon == "medicines" and "medicine_used" in out:
            target_keys.add("medicine_used")

        if isinstance(value, list) and canon == "medicines":
            cleaned_list = [_clean_text(str(m)) for m in value if _clean_text(str(m))]
            for tk in target_keys:
                out[tk] = cleaned_list
        elif isinstance(value, str):
            cleaned = _clean_text(value)
            for tk in target_keys:
                out[tk] = cleaned
        else:
            for tk in target_keys:
                out[tk] = value
    return out


def _detect_flag_override(
    checklist: dict[str, Any],
    edits: dict[str, Any],
) -> bool:
    """Check if doctor edited any field that had a checklist flag."""
    if not isinstance(checklist, dict):
        return False
    flagged_fields = {
        _canonical_field(str(f.get("field") or "").split("[")[0])
        for f in (checklist.get("flags", []) or [])
        if isinstance(f, dict)
    }
    edited_fields = {_canonical_field(k) for k in edits.keys()}
    return bool(flagged_fields & edited_fields)


# ---------------------------------------------------------------------------
# Confidence computation
# ---------------------------------------------------------------------------


def _compute_verified_confidence(
    structured: dict[str, Any],
    checklist: dict[str, Any],
    edits: dict[str, Any],
    decision: str,
) -> float:
    """Re-score confidence after doctor intervention.

    - If doctor approved and fixed flagged fields → high confidence
    - If doctor approved but left critical flags unresolved → moderate
    - If doctor rejected → confidence reflects data quality, not decision
    - If doctor queried → lower confidence (pending resolution)
    """
    base = _score_field_completeness(structured)

    # Doctor edits improve confidence (they verified the data)
    edit_bonus = min(0.15, len(edits) * 0.04)

    # If doctor overrode flags they addressed, that's a correction
    flags_overridden = _detect_flag_override(checklist, edits)
    override_bonus = 0.10 if flags_overridden else 0.0

    # Decision impact
    if decision == "approve":
        # Unresolved critical flags still hurt confidence
        unresolved_critical = sum(
            1
            for f in checklist.get("flags", [])
            if f.get("severity") == "critical"
            and _canonical_field(str(f.get("field") or "").split("[")[0]) not in {_canonical_field(k) for k in edits.keys()}
        )
        critical_penalty = unresolved_critical * 0.12
        final = base + edit_bonus + override_bonus - critical_penalty
    elif decision == "reject":
        # Rejection is a valid decision; confidence reflects data quality
        final = base * 0.8
    else:  # query
        final = base * 0.6

    return max(0.0, min(1.0, final))


def _score_field_completeness(data: dict[str, Any]) -> float:
    """Score 0.0–1.0 based on how many fields are populated."""
    weights: dict[str, float] = {
        "doctor_name": 0.15,
        "diagnosis": 0.25,
        "medicines": 0.25,
        "hospital": 0.15,
        # Accept either DOA/DOD or a single `date` field.
        "doa": 0.10,
        "duration": 0.10,
    }
    score = 0.0
    for field, weight in weights.items():
        value = data.get(field)
        if field == "doctor_name":
            value = data.get("doctor_name") or data.get("treating_doctor")
        elif field == "hospital":
            value = data.get("hospital") or data.get("hospital_name")
        elif field == "medicines":
            value = data.get("medicines") or data.get("medicine_used")
        elif field == "doa":
            value = data.get("doa") or data.get("dod") or data.get("date")

        if isinstance(value, str) and value.strip():
            score += weight
        elif isinstance(value, list) and value:
            score += weight
    return score


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _coerce_edited_fields(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in _EDITABLE_FIELDS:
            continue
        if isinstance(value, list):
            out[key] = [str(v) for v in value]
        elif value is not None:
            out[key] = str(value)
        else:
            out[key] = ""
    return out


def _clean_notes(raw: str) -> str:
    return _clean_text(raw or "")


def _clean_text(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:2000]


__all__ = [
    "DoctorVerificationError",
    "run_doctor_verification",
    "verify_doctor_decision",
    "normalize_decision",
]
