from __future__ import annotations

import re
from typing import Any

_DL_HINT_RE = re.compile(r"\b(?:dl|d\.l\.|drug\s*licen(?:s|c)e)\b", re.IGNORECASE)
_DL_CAPTURE_RE = re.compile(
    r"(?i)\b(?:dl|d\.l\.|drug\s*licen(?:s|c)e)\b\s*(?:no\.?|number|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9\/\-.]{4,29})\b"
)


def extract_drug_license(text: str) -> str:
    t = str(text or "")
    m = _DL_CAPTURE_RE.search(t)
    if not m:
        return ""
    return m.group(1).strip().upper().strip(".,;:-")


def is_plausible_drug_license(value: Any) -> bool:
    v = str(value or "").strip().upper()
    if not v:
        return False
    if len(v) < 5 or len(v) > 30:
        return False
    if re.fullmatch(r"0+", v):
        return False
    # allow alnum plus typical separators
    if not re.fullmatch(r"[A-Z0-9\/\-.]+", v):
        return False
    if not re.search(r"\d", v):
        return False
    return True


def verify_drug_license_best_effort(license_no: str) -> dict[str, Any]:
    value = str(license_no or "").strip().upper()
    if not value:
        return {"valid": False, "license_no": "", "status": "missing"}
    if not is_plausible_drug_license(value):
        return {"valid": False, "license_no": value, "status": "invalid_format"}
    form_type = ""
    # common form types mentioned in licenses
    m = re.search(r"\b(20B|21B|20|21)\b", value)
    if m:
        form_type = m.group(1)
    out: dict[str, Any] = {"valid": True, "license_no": value, "status": "valid"}
    if form_type:
        out["form_type"] = form_type
    return out


__all__ = ["extract_drug_license", "is_plausible_drug_license", "verify_drug_license_best_effort"]
