from __future__ import annotations

import re

from app.infrastructure.banking.razorpay_ifsc import (
    IfscNetworkError,
    IfscNotFoundError,
    IfscServiceError,
    IfscVerificationDisabledError,
    fetch_ifsc_payload,
)
from app.schemas.auth import IfscVerificationResponse


class InvalidIfscFormatError(ValueError):
    pass


def normalize_ifsc_code(value: str | None) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().upper())


def coerce_optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text_value = str(value).strip().lower()
    if text_value in {"1", "true", "yes", "y"}:
        return True
    if text_value in {"0", "false", "no", "n"}:
        return False
    return None


def verify_ifsc_code(ifsc_code: str) -> IfscVerificationResponse:
    normalized_ifsc = normalize_ifsc_code(ifsc_code)
    if not normalized_ifsc:
        raise InvalidIfscFormatError("IFSC code is required.")
    if not re.fullmatch(r"^[A-Z]{4}0[A-Z0-9]{6}$", normalized_ifsc):
        raise InvalidIfscFormatError("Invalid IFSC format.")

    payload = fetch_ifsc_payload(normalized_ifsc)

    bank_name = str(payload.get("BANK") or "").strip()
    branch_name = str(payload.get("BRANCH") or "").strip()
    return IfscVerificationResponse(
        ifsc_code=normalized_ifsc,
        valid=bool(bank_name or branch_name),
        bank_name=bank_name,
        branch_name=branch_name,
        address=str(payload.get("ADDRESS") or "").strip(),
        city=str(payload.get("CITY") or "").strip(),
        district=str(payload.get("DISTRICT") or "").strip(),
        state=str(payload.get("STATE") or "").strip(),
        contact=str(payload.get("CONTACT") or "").strip(),
        micr=str(payload.get("MICR") or "").strip(),
        bank_code=str(payload.get("BANKCODE") or "").strip(),
        upi=coerce_optional_bool(payload.get("UPI")),
        neft=coerce_optional_bool(payload.get("NEFT")),
        rtgs=coerce_optional_bool(payload.get("RTGS")),
        imps=coerce_optional_bool(payload.get("IMPS")),
        source="razorpay_ifsc",
        raw=payload if isinstance(payload, dict) else {},
    )


__all__ = [
    "IfscNetworkError",
    "IfscNotFoundError",
    "IfscServiceError",
    "IfscVerificationDisabledError",
    "InvalidIfscFormatError",
    "coerce_optional_bool",
    "normalize_ifsc_code",
    "verify_ifsc_code",
]

