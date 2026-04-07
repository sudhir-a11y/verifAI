from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from app.infrastructure.integrations.apisetu_gst import (
    ApisetuGstConfigError,
    ApisetuGstDisabledError,
    ApisetuGstNetworkError,
    ApisetuGstServiceError,
    fetch_taxpayer_details,
)

# GSTIN format: 15 chars
_GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b", re.IGNORECASE)

_GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_GSTIN_CHAR_TO_VAL = {c: i for i, c in enumerate(_GSTIN_CHARS)}


def extract_gstin(text: str) -> str:
    m = _GSTIN_RE.search(str(text or ""))
    if not m:
        return ""
    return m.group(0).upper()


def is_valid_gstin(gstin: Any) -> bool:
    """Validate GSTIN using the official checksum algorithm.

    Ref: GSTN check digit is mod-36 over base-36 chars with alternating weights.
    """
    g = str(gstin or "").strip().upper()
    if len(g) != 15:
        return False
    if not _GSTIN_RE.fullmatch(g):
        return False

    # Last char is check digit
    body = g[:-1]
    check = g[-1]

    factor = 2
    total = 0
    n = 36
    for ch in reversed(body):
        code_point = _GSTIN_CHAR_TO_VAL.get(ch)
        if code_point is None:
            return False
        addend = factor * code_point
        factor = 1 if factor == 2 else 2
        addend = (addend // n) + (addend % n)
        total += addend
    remainder = total % n
    calc = (n - remainder) % n
    calc_char = _GSTIN_CHARS[calc]
    return calc_char == check


def verify_gstin_best_effort(gstin: str) -> dict[str, Any]:
    """Best-effort GST verification.

    For now this is strict format+checksum validation (no external GSTN lookup).
    """
    value = str(gstin or "").strip().upper()
    if not value:
        return {"valid": False, "gstin": "", "status": "missing", "source": "basic"}

    if not is_valid_gstin(value):
        return {"valid": False, "gstin": value, "status": "invalid_format", "source": "basic"}

    return {"valid": True, "gstin": value, "status": "valid_basic", "source": "basic"}


_GST_STATE_CODE_TO_NAME: dict[str, list[str]] = {
    "07": ["delhi", "nct of delhi"],
    "27": ["maharashtra", "mh"],
    "29": ["karnataka", "ka"],
    "33": ["tamil nadu", "tn"],
    "24": ["gujarat", "gj"],
    "06": ["haryana", "hr"],
    "09": ["uttar pradesh", "up"],
    "08": ["rajasthan", "rj"],
    "10": ["bihar", "br"],
    "23": ["madhya pradesh", "mp"],
    "19": ["west bengal", "wb"],
}


def gst_state_code_from_state_name(state: str) -> str:
    s = re.sub(r"\s+", " ", str(state or "").strip().lower())
    s = s.replace("&", "and")
    if not s:
        return ""
    for code, names in _GST_STATE_CODE_TO_NAME.items():
        for n in names:
            if n and (s == n or n in s or s in n):
                return code
    return ""


def _norm_name(value: str) -> str:
    t = str(value or "").strip().lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t


def _name_similarity(a: str, b: str) -> float:
    na = _norm_name(a)
    nb = _norm_name(b)
    if not na or not nb:
        return 0.0
    return float(SequenceMatcher(None, na, nb).ratio())


def verify_gstin_via_apisetu_best_effort(
    *,
    gstin: str,
    expected_name: str | None = None,
    expected_state: str | None = None,
) -> dict[str, Any]:
    """Verify GSTIN using APISetu taxpayer API when configured.

    Falls back to basic checksum validation on any provider failure.
    """
    basic = verify_gstin_best_effort(gstin)
    if not basic.get("valid"):
        return basic

    try:
        raw = fetch_taxpayer_details(gstin)
    except (ApisetuGstDisabledError, ApisetuGstConfigError):
        return basic
    except (ApisetuGstNetworkError, ApisetuGstServiceError):
        # Keep basic validity, but mark provider unavailable
        return {**basic, "provider_status": "unavailable"}

    def _nested(obj: dict[str, Any], *path: str) -> Any:
        cur: Any = obj
        for key in path:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(key)
        return cur

    # Defensive parsing: APISetu taxpayer payloads vary across versions/providers.
    legal_name = (
        raw.get("legalNameOfBusiness")
        or raw.get("legalName")
        or raw.get("lgnm")
        or raw.get("legal_name")
        or raw.get("taxpayerName")
        or ""
    )
    trade_name = (
        raw.get("tradeName")
        or raw.get("trade_name")
        or raw.get("tradeNam")
        or raw.get("trade")
        or ""
    )
    status = (
        raw.get("gstnStatus")
        or raw.get("status")
        or raw.get("sts")
        or raw.get("gstStatus")
        or raw.get("registrationStatus")
        or ""
    )
    provider_gstin = raw.get("gstIdentificationNumber") or raw.get("gstin") or raw.get("gstIdentificationNo") or ""
    provider_state = (
        _nested(raw, "principalPlaceOfBusinessFields", "principalPlaceOfBusinessAddress", "stateName")
        or raw.get("stateName")
        or raw.get("state")
        or ""
    )
    status_norm = str(status or "").strip().lower()
    is_active = status_norm in {"active", "registered", "valid"} or ("active" in status_norm)

    gst_state_code = str(gstin or "").strip()[:2]
    expected_code = gst_state_code_from_state_name(expected_state or "")
    state_match: bool | None = None
    if expected_state:
        # Prefer direct state name match when provider includes it
        if provider_state:
            state_match = _name_similarity(str(expected_state), str(provider_state)) >= 0.70
        elif expected_code:
            state_match = (gst_state_code == expected_code)
    elif expected_code:
        state_match = (gst_state_code == expected_code)

    name_match = None
    if expected_name:
        score = max(_name_similarity(expected_name, str(legal_name)), _name_similarity(expected_name, str(trade_name)))
        name_match = score >= 0.60

    valid = bool(is_active and (state_match is not False) and (name_match is not False))
    status_out = "active" if is_active else (status_norm or "unknown")
    reason = ""
    if not is_active:
        reason = "inactive_or_cancelled"
    elif state_match is False:
        reason = "state_mismatch"
    elif name_match is False:
        reason = "name_mismatch"

    return {
        "valid": valid,
        "gstin": str(gstin).strip().upper(),
        "status": status_out,
        "legal_name": str(legal_name or ""),
        "trade_name": str(trade_name or ""),
        "state_code": gst_state_code,
        "state_name": str(provider_state or ""),
        "provider_gstin": str(provider_gstin or ""),
        "state_match": state_match,
        "name_match": name_match,
        "reason": reason,
        "source": "apisetu",
    }


__all__ = [
    "extract_gstin",
    "gst_state_code_from_state_name",
    "is_valid_gstin",
    "verify_gstin_best_effort",
    "verify_gstin_via_apisetu_best_effort",
]
