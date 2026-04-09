"""Checklist engine for post-OCR/structuring validation.

Pipeline (high-level): OCR → extraction → structuring → validation → decision

This module validates *structured claim data* (the output of the claim
structuring step, e.g. `/api/v1/claims/{claim_id}/structured-data`), and
returns flags + a severity + a recommendation + a confidence score.

It is intentionally lightweight and rule-based: the goal is to catch
missing/invalid fields early so downstream checklist/decision/reporting
steps can behave predictably.

Return shape (stable):

    {
      "flags": [{"field": "...", "code": "...", "message": "...", "severity": "..."}],
      "severity": "low" | "medium" | "high",
      "recommendation": "APPROVE" | "QUERY" | "REJECT",
      "confidence": 0.0
    }
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_checklist(
    structured: dict[str, Any],
    *,
    require_hospital: bool = True,
    require_doctor: bool = True,
    require_medicines: bool = True,
    require_diagnosis: bool = True,
    require_date: bool = True,
) -> dict[str, Any]:
    """Validate structured OCR data and return a checklist result.

    Parameters
    ----------
    structured:
        Dict of structured claim data. Supported inputs include:

        - Claim structured data (preferred): keys like ``treating_doctor``,
          ``hospital_name``, ``diagnosis``, ``medicine_used``, ``doa``, ``dod``,
          ``claim_amount``, etc.
        - Legacy/alternate structurer output: keys like ``doctor_name``,
          ``hospital``, ``medicines``, ``date``.

    Returns
    -------
    dict with keys: ``flags``, ``severity``, ``recommendation``, ``confidence``.

    ``flags`` is a list of dicts, each with ``field``, ``code``,
    ``message``, ``severity`` (``"warning"`` or ``"critical"``).

    ``severity`` is the worst flag severity: ``"low"``, ``"medium"``, ``"high"``.

    ``recommendation`` is one of ``"APPROVE"``, ``"QUERY"``, ``"REJECT"``.

    ``confidence`` is a float ``0.0–1.0`` reflecting overall data quality.
    """

    data = _coerce_structured_input(structured)
    flags: list[dict[str, str]] = []

    # --- Required-field checks ---
    if require_doctor and not data.get("doctor_name"):
        flags.append(_flag("doctor_name", "MISSING_DOCTOR", "Treating doctor is missing", severity="critical"))

    if require_diagnosis and not data.get("diagnosis"):
        flags.append(_flag("diagnosis", "MISSING_DIAGNOSIS", "Diagnosis is missing", severity="critical"))

    if require_medicines and not data.get("medicines"):
        flags.append(_flag("medicines", "MISSING_MEDICINES", "Medicines used is missing", severity="warning"))

    if require_hospital and not data.get("hospital"):
        flags.append(_flag("hospital", "MISSING_HOSPITAL", "Hospital name is missing", severity="critical"))

    if require_date and not (data.get("doa") or data.get("dod") or data.get("date")):
        flags.append(_flag("doa", "MISSING_DATES", "DOA/DOD is missing", severity="warning"))

    # --- Quality checks (only run when the field has data) ---

    if data.get("doctor_name"):
        flags.extend(_check_doctor_name(data["doctor_name"]))

    if data.get("diagnosis"):
        flags.extend(_check_diagnosis(data["diagnosis"]))

    if data.get("medicines"):
        flags.extend(_check_medicines(data["medicines"]))

    # DOA/DOD validation: prefer DOA/DOD; fall back to a single `date` field.
    if data.get("doa") or data.get("dod"):
        flags.extend(_check_doa_dod(data.get("doa", ""), data.get("dod", "")))
    elif data.get("date"):
        flags.extend(_check_single_date(data["date"]))

    if data.get("claim_amount"):
        flags.extend(_check_claim_amount(data["claim_amount"]))

    # --- Aggregate ---

    severity = _worst_severity(flags)
    recommendation = _recommendation(severity, flags)
    confidence = _compute_confidence(data, flags)

    return {
        "flags": flags,
        "severity": severity,
        "recommendation": recommendation,
        "confidence": round(confidence, 4),
    }


# ---------------------------------------------------------------------------
# Field-level validators
# ---------------------------------------------------------------------------


_DOCTOR_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{2,}$")
_SUSPICIOUS_NAME_CHARS = re.compile(r"[\d@#$%^&*!=<>/?]")
_GARBAGE_RE = re.compile(
    r"^(unknown|not\s*found|none|n/?a|nil|blank|no\s*data|missing)$", re.I
)
_MEDICINE_MIN_LEN = 2


def _check_doctor_name(value: str) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    cleaned = value.strip()
    if not cleaned:
        return flags  # handled by MISSING_DOCTOR

    if _GARBAGE_RE.match(cleaned):
        flags.append(
            _flag(
                "doctor_name",
                "INVALID_DOCTOR_NAME",
                "Doctor name looks like a placeholder",
                severity="critical",
            )
        )
    elif _SUSPICIOUS_NAME_CHARS.search(cleaned):
        flags.append(
            _flag(
                "doctor_name",
                "SUSPICIOUS_DOCTOR_NAME",
                "Doctor name contains unexpected characters",
                severity="warning",
            )
        )
    elif len(cleaned) <= 4:
        flags.append(
            _flag(
                "doctor_name",
                "SHORT_DOCTOR_NAME",
                "Doctor name is unusually short",
                severity="warning",
            )
        )
    return flags


_SHORT_DIAGNOSIS_THRESHOLD = 3
_LONG_DIAGNOSIS_THRESHOLD = 200


def _check_diagnosis(value: str) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    cleaned = value.strip()
    if not cleaned:
        return flags

    if _GARBAGE_RE.match(cleaned):
        flags.append(
            _flag(
                "diagnosis",
                "INVALID_DIAGNOSIS",
                "Diagnosis looks like a placeholder",
                severity="critical",
            )
        )
    elif len(cleaned) < _SHORT_DIAGNOSIS_THRESHOLD:
        flags.append(
            _flag(
                "diagnosis",
                "SHORT_DIAGNOSIS",
                "Diagnosis is very short — may be incomplete",
                severity="warning",
            )
        )
    elif len(cleaned) > _LONG_DIAGNOSIS_THRESHOLD:
        flags.append(
            _flag(
                "diagnosis",
                "LONG_DIAGNOSIS",
                "Diagnosis is unusually long — may include non-diagnosis text",
                severity="warning",
            )
        )
    return flags


def _check_medicines(medicines: list[str]) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    if not isinstance(medicines, list):
        flags.append(
            _flag(
                "medicines",
                "INVALID_MEDICINES_FORMAT",
                "Medicines field is not a list",
                severity="critical",
            )
        )
        return flags

    for idx, med in enumerate(medicines):
        cleaned = str(med or "").strip()
        if not cleaned:
            continue
        if _GARBAGE_RE.match(cleaned):
            flags.append(
                _flag(
                    f"medicines[{idx}]",
                    "INVALID_MEDICINE_ENTRY",
                    f"Medicine entry #{idx + 1} looks like a placeholder: '{cleaned}'",
                    severity="warning",
                )
            )
        elif len(cleaned) < _MEDICINE_MIN_LEN:
            flags.append(
                _flag(
                    f"medicines[{idx}]",
                    "SHORT_MEDICINE_ENTRY",
                    f"Medicine entry #{idx + 1} is very short: '{cleaned}'",
                    severity="warning",
                )
            )
    return flags


_FUTURE_DATE_TOLERANCE_DAYS = 1


def _check_date(value: str) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    cleaned = str(value or "").strip()
    if not cleaned:
        return flags

    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", cleaned)
    if not m:
        flags.append(
            _flag(
                "date",
                "INVALID_DATE_FORMAT",
                f"Date is not in ISO format: '{cleaned}'",
                severity="critical",
            )
        )
        return flags

    try:
        parsed = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except Exception:
        flags.append(
            _flag(
                "date",
                "INVALID_DATE",
                f"Date could not be parsed: '{cleaned}'",
                severity="critical",
            )
        )
        return flags

    today = date.today()
    diff = (parsed - today).days
    if diff > _FUTURE_DATE_TOLERANCE_DAYS:
        flags.append(
            _flag(
                "date",
                "FUTURE_DATE",
                f"Date is {diff} days in the future: '{cleaned}'",
                severity="critical",
            )
        )
    elif diff < -365 * 10:
        flags.append(
            _flag(
                "date",
                "VERY_OLD_DATE",
                f"Date is more than 10 years old: '{cleaned}'",
                severity="warning",
            )
        )
    return flags


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def _worst_severity(flags: list[dict[str, str]]) -> str:
    if not flags:
        return "low"
    if any(f["severity"] == "critical" for f in flags):
        return "high"
    return "medium"


def _recommendation(severity: str, flags: list[dict[str, str]]) -> str:
    """Decide what to do next based on severity and flag composition."""
    if severity == "low":
        return "APPROVE"

    critical_missing = sum(
        1 for f in flags if str(f.get("code", "")).startswith("MISSING_") and f.get("severity") == "critical"
    )
    if severity == "high" and critical_missing >= 2:
        return "REJECT"

    return "QUERY"


_CRITICAL_FIELD_WEIGHT = {
    "doctor_name": 0.20,
    "diagnosis": 0.20,
    "medicines": 0.25,
    "hospital": 0.15,
    "doa": 0.10,
    "duration": 0.10,
}


def _compute_confidence(
    data: dict[str, Any], flags: list[dict[str, str]]
) -> float:
    """Score 0.0–1.0 based on field presence and flag penalties."""
    score = 0.0

    # Award points for populated fields
    for field, weight in _CRITICAL_FIELD_WEIGHT.items():
        value = data.get(field)
        if field == "doa":
            # Date weight: accept DOA/DOD or a single `date` field.
            value = data.get("doa") or data.get("dod") or data.get("date")
        present = False
        if isinstance(value, str) and value.strip():
            present = True
        elif isinstance(value, list) and value:
            present = True
        if present:
            score += weight

    # Deduct for flags (weighted by severity)
    flag_penalties = {
        "critical": 0.15,
        "warning": 0.05,
    }
    for f in flags:
        score -= flag_penalties.get(f["severity"], 0.0)

    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------


def _flag(
    field: str,
    code: str,
    message: str,
    *,
    severity: str = "warning",
) -> dict[str, str]:
    return {
        "field": field,
        "code": code,
        "message": message,
        "severity": severity,
    }


def _coerce_structured_input(raw: Any) -> dict[str, Any]:
    """Ensure we always work with a well-shaped dict.

    Supports multiple structured-data shapes:
    - claim_structured_data (treating_doctor, hospital_name, medicine_used, doa, dod, claim_amount)
    - legacy structurer output (doctor_name, hospital, medicines, date)
    """
    if not isinstance(raw, dict):
        return {
            "doctor_name": "",
            "diagnosis": "",
            "medicines": [],
            "duration": "",
            "hospital": "",
            "date": "",
            "doa": "",
            "dod": "",
            "claim_amount": "",
        }

    out: dict[str, Any] = {}
    # Canonicalize keys from claim_structured_data response
    doctor = raw.get("doctor_name")
    if doctor is None:
        doctor = raw.get("treating_doctor")
    hospital = raw.get("hospital")
    if hospital is None:
        hospital = raw.get("hospital_name")
    diagnosis = raw.get("diagnosis")
    duration = raw.get("duration")
    out["doctor_name"] = str(doctor) if doctor is not None else ""
    out["hospital"] = str(hospital) if hospital is not None else ""
    out["diagnosis"] = str(diagnosis) if diagnosis is not None else ""
    out["duration"] = str(duration) if duration is not None else ""

    out["doa"] = str(raw.get("doa") or "").strip()
    out["dod"] = str(raw.get("dod") or "").strip()
    out["date"] = str(raw.get("date") or "").strip()
    out["claim_amount"] = str(raw.get("claim_amount") or "").strip()

    meds = raw.get("medicines")
    if meds is None:
        meds = raw.get("medicine_used")
    if isinstance(meds, list):
        out["medicines"] = [str(m).strip() for m in meds if str(m).strip()]
    elif isinstance(meds, str):
        # Split on newlines and semicolons only — NOT commas.
        # Medicine names commonly contain commas (e.g. "Cefoperazone, Sulbactam").
        parts = [p.strip() for p in re.split(r"[\n;]+", meds) if p.strip()]
        out["medicines"] = parts
    else:
        out["medicines"] = []

    return out


__all__ = [
    "run_checklist",
    "check_doctor_name",
    "check_diagnosis",
    "check_medicines",
    "check_date",
]


# Public wrappers (unit-test friendly / stable API)


def check_doctor_name(value: str) -> list[dict[str, str]]:
    return _check_doctor_name(str(value or ""))


def check_diagnosis(value: str) -> list[dict[str, str]]:
    return _check_diagnosis(str(value or ""))


def check_medicines(value: Any) -> list[dict[str, str]]:
    return _check_medicines(value if value is not None else [])


def check_date(value: str) -> list[dict[str, str]]:
    return _check_single_date(str(value or ""))


def _parse_date_loose(value: str) -> tuple[date | None, str | None]:
    raw = str(value or "").strip()
    if not raw:
        return None, None

    # ISO 8601 date
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), None
        except Exception:
            return None, "INVALID_DATE"

    # DD/MM/YYYY or DD-MM-YYYY
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", raw)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))), None
        except Exception:
            return None, "INVALID_DATE"

    return None, "INVALID_DATE_FORMAT"


def _check_single_date(value: str) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    cleaned = str(value or "").strip()
    if not cleaned:
        return flags

    parsed, err = _parse_date_loose(cleaned)
    if not parsed:
        flags.append(
            _flag(
                "date",
                err or "INVALID_DATE_FORMAT",
                f"Date could not be parsed: '{cleaned}'",
                severity="critical",
            )
        )
        return flags

    today = date.today()
    diff = (parsed - today).days
    if diff > _FUTURE_DATE_TOLERANCE_DAYS:
        flags.append(
            _flag(
                "date",
                "FUTURE_DATE",
                f"Date is {diff} days in the future: '{cleaned}'",
                severity="critical",
            )
        )
    elif diff < -365 * 10:
        flags.append(
            _flag(
                "date",
                "VERY_OLD_DATE",
                f"Date is more than 10 years old: '{cleaned}'",
                severity="warning",
            )
        )
    return flags


def _check_doa_dod(doa: str, dod: str) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    doa_parsed, doa_err = _parse_date_loose(doa)
    dod_parsed, dod_err = _parse_date_loose(dod)

    if doa and not doa_parsed:
        flags.append(_flag("doa", doa_err or "INVALID_DOA", f"DOA could not be parsed: '{doa}'", severity="warning"))
    if dod and not dod_parsed:
        flags.append(_flag("dod", dod_err or "INVALID_DOD", f"DOD could not be parsed: '{dod}'", severity="warning"))

    if doa_parsed and dod_parsed and dod_parsed < doa_parsed:
        flags.append(_flag("dod", "DOD_BEFORE_DOA", "DOD is earlier than DOA", severity="critical"))

    # Basic sanity: far future
    today = date.today()
    for field, parsed, raw in (("doa", doa_parsed, doa), ("dod", dod_parsed, dod)):
        if not parsed:
            continue
        diff = (parsed - today).days
        if diff > _FUTURE_DATE_TOLERANCE_DAYS:
            flags.append(_flag(field, "FUTURE_DATE", f"{field.upper()} is {diff} days in the future: '{raw}'", severity="critical"))
        elif diff < -365 * 10:
            flags.append(_flag(field, "VERY_OLD_DATE", f"{field.upper()} is more than 10 years old: '{raw}'", severity="warning"))

    return flags


def _check_claim_amount(value: str) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    raw = str(value or "").strip()
    if not raw:
        return flags
    cleaned = re.sub(r"[^0-9.\\-]", "", raw)
    if cleaned in {"", "-", ".", "-."}:
        flags.append(_flag("claim_amount", "INVALID_CLAIM_AMOUNT", f"Claim amount is invalid: '{raw}'", severity="warning"))
        return flags
    try:
        amount = float(cleaned)
    except Exception:
        flags.append(_flag("claim_amount", "INVALID_CLAIM_AMOUNT", f"Claim amount is invalid: '{raw}'", severity="warning"))
        return flags
    if amount < 0:
        flags.append(_flag("claim_amount", "NEGATIVE_CLAIM_AMOUNT", f"Claim amount is negative: '{raw}'", severity="critical"))
    if amount == 0:
        flags.append(_flag("claim_amount", "ZERO_CLAIM_AMOUNT", "Claim amount is 0", severity="warning"))
    return flags
