from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any

from app.core.config import settings
from app.infrastructure.integrations.abdm_hpr import (
    AbdmHprAuthError,
    AbdmHprConfigError,
    AbdmHprDisabledError,
    AbdmHprNetworkError,
    AbdmHprServiceError,
    search_doctor_by_registration_number,
)

logger = logging.getLogger(__name__)


def _norm_name(value: str) -> str:
    t = str(value or "").strip().lower()
    t = re.sub(r"^\s*(dr\.?|doctor)\s+", "", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t


def _name_similarity(a: str, b: str) -> float:
    na = _norm_name(a)
    nb = _norm_name(b)
    if not na or not nb:
        return 0.0
    return float(SequenceMatcher(None, na, nb).ratio())


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _pick_candidate_fields(candidate: dict[str, Any]) -> tuple[str, str, str, str]:
    name = _coerce_str(
        candidate.get("name")
        or candidate.get("fullName")
        or candidate.get("doctorName")
        or candidate.get("practitionerName")
    )
    council = _coerce_str(
        candidate.get("council")
        or candidate.get("registrationCouncil")
        or candidate.get("councilName")
        or candidate.get("stateMedicalCouncil")
        or candidate.get("stateCouncil")
    )
    speciality = _coerce_str(
        candidate.get("speciality")
        or candidate.get("specialization")
        or candidate.get("specialityName")
    )
    status = _coerce_str(
        candidate.get("status")
        or candidate.get("registrationStatus")
        or candidate.get("state")
        or "unknown"
    )
    return name, council, speciality, status


def _status_is_active(status: str) -> bool:
    s = str(status or "").strip().lower()
    if not s:
        return False
    if s in {"active", "verified", "registered", "valid"}:
        return True
    return "active" in s or "verified" in s


def _council_matches_state(*, council: str, state: str) -> bool:
    c = str(council or "").strip().lower()
    s = str(state or "").strip().lower()
    if not c or not s:
        return False
    # Common variants: "Delhi Medical Council", "NCT of Delhi", etc.
    if s in c:
        return True
    if c in s:
        return True
    return False


def verify_doctor_registration_from_candidates(
    *,
    name: str,
    registration_number: str,
    state: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Pure matching logic for doctor registry results.

    Returns a stable dict suitable for API responses:
      {"valid", "doctor_name", "council", "speciality", "status"}
    """
    requested_name = _coerce_str(name)
    requested_state = _coerce_str(state)
    reg = _coerce_str(registration_number)

    if not reg:
        return {"valid": False, "doctor_name": "", "council": "", "speciality": "", "status": "invalid_request"}

    best: dict[str, Any] | None = None
    best_score = 0.0
    best_fields: tuple[str, str, str, str] = ("", "", "", "")

    for cand in candidates or []:
        if not isinstance(cand, dict):
            continue
        cand_name, cand_council, cand_speciality, cand_status = _pick_candidate_fields(cand)
        name_score = _name_similarity(requested_name, cand_name)
        council_ok = _council_matches_state(council=cand_council, state=requested_state)
        council_score = 1.0 if council_ok else 0.0

        # Weighted score prioritizes name match, then council match.
        score = (0.75 * name_score) + (0.25 * council_score)
        if score > best_score:
            best = cand
            best_score = score
            best_fields = (cand_name, cand_council, cand_speciality, cand_status)

    if best is None:
        return {"valid": False, "doctor_name": "", "council": "", "speciality": "", "status": "not_found"}

    cand_name, cand_council, cand_speciality, cand_status = best_fields
    active = _status_is_active(cand_status)
    council_ok = _council_matches_state(council=cand_council, state=requested_state)
    name_ok = _name_similarity(requested_name, cand_name) >= 0.60

    # Verification contract: use reg no (search), name, and state council.
    valid = bool(active and name_ok and council_ok)
    status_out = (cand_status or "unknown").strip().lower()
    if active:
        status_out = "active"

    return {
        "valid": valid,
        "doctor_name": cand_name,
        "council": cand_council,
        "speciality": cand_speciality,
        "status": status_out,
    }


def verify_doctor_registration(
    *,
    name: str,
    registration_number: str,
    state: str,
) -> dict[str, Any]:
    """Verify doctor registration using ABDM HPR search-by-registration API."""
    if not settings.abdm_hpr_enabled:
        raise AbdmHprDisabledError("ABDM HPR integration is disabled.")

    candidates = search_doctor_by_registration_number(registration_number)
    return verify_doctor_registration_from_candidates(
        name=name,
        registration_number=registration_number,
        state=state,
        candidates=candidates,
    )


def verify_doctor_registration_with_fallback(
    *,
    name: str,
    registration_number: str,
    state: str,
) -> dict[str, Any]:
    """Non-blocking wrapper: returns an 'unavailable' response on failures."""
    try:
        return verify_doctor_registration(
            name=name,
            registration_number=registration_number,
            state=state,
        )
    except (AbdmHprDisabledError, AbdmHprConfigError, AbdmHprAuthError) as exc:
        logger.warning("Doctor registry verification unavailable (config/auth): %s", exc)
        return {"valid": False, "doctor_name": "", "council": "", "speciality": "", "status": "unavailable"}
    except (AbdmHprNetworkError, AbdmHprServiceError) as exc:
        logger.warning("Doctor registry verification unavailable (network/service): %s", exc)
        return {"valid": False, "doctor_name": "", "council": "", "speciality": "", "status": "unavailable"}
    except Exception as exc:
        logger.error("Doctor registry verification unexpected error: %s", exc)
        return {"valid": False, "doctor_name": "", "council": "", "speciality": "", "status": "unavailable"}


__all__ = [
    "verify_doctor_registration",
    "verify_doctor_registration_from_candidates",
    "verify_doctor_registration_with_fallback",
]

