"""ABDM HPR doctor verification use cases.

Business logic for verifying doctor identities via the ABDM Healthcare
Professionals Registry during login.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.infrastructure.cache import cache as _cache
from app.infrastructure.integrations.abdm_hpr import (
    AbdmHprConfigError,
    AbdmHprAuthError,
    AbdmHprDisabledError,
    AbdmHprDoctorNotFoundError,
    AbdmHprNetworkError,
    AbdmHprServiceError,
    verify_doctor,
)

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# Custom exceptions (domain-level)
# ────────────────────────────────────────────────────────────────────

class DoctorVerificationError(RuntimeError):
    """Raised when doctor verification fails for a known reason."""
    pass


class DoctorNotVerifiedError(DoctorVerificationError):
    """Raised when the doctor exists in HPR but is not in an active/verified status."""
    pass


# ────────────────────────────────────────────────────────────────────
# Cache helpers
# ────────────────────────────────────────────────────────────────────

_CACHE_PREFIX = "abdm_hpr:"


def _cache_key(hpr_id: str) -> str:
    return f"{_CACHE_PREFIX}verify:{hpr_id}"


def _get_cached(hpr_id: str) -> dict[str, Any] | None:
    """Retrieve cached verification result."""
    return _cache.get(_cache_key(hpr_id))


def _set_cached(hpr_id: str, result: dict[str, Any]) -> None:
    """Cache verification result with configured TTL."""
    ttl = int(settings.abdm_hpr_cache_ttl_seconds or 3600)
    _cache.set(_cache_key(hpr_id), result, ttl_seconds=ttl)


def invalidate_hpr_cache(hpr_id: str) -> None:
    """Invalidate cached verification for a specific HPR ID."""
    _cache.delete(_cache_key(hpr_id))


# ────────────────────────────────────────────────────────────────────
# Public use-case functions
# ────────────────────────────────────────────────────────────────────

def verify_doctor_for_login(hpr_id: str) -> dict[str, Any]:
    """Verify a doctor via ABDM HPR for login authentication.

    This is the main entry point called during the login flow for doctor
    role users. It:
      1. Checks configuration is enabled
      2. Consults the cache before making an API call
      3. Calls the HPR API to verify the doctor
      4. Ensures the doctor status is active/verified
      5. Caches the result
      6. Returns the normalized verification result

    Raises:
        AbdmHprDisabledError: If ABDM HPR integration is disabled.
        DoctorNotVerifiedError: If doctor exists but is not active/verified.
        DoctorVerificationError: For other verification failures.
    """
    if not settings.abdm_hpr_enabled:
        raise AbdmHprDisabledError("ABDM HPR integration is disabled.")

    hpr_id_stripped = str(hpr_id or "").strip()
    if not hpr_id_stripped:
        raise DoctorVerificationError("HPR ID is required for doctor verification.")

    # Check cache first
    cached = _get_cached(hpr_id_stripped)
    if cached is not None:
        logger.debug("Cache hit for ABDM HPR verification: hpr_id=%s", hpr_id_stripped)
        if not cached.get("verified"):
            raise DoctorNotVerifiedError(
                f"Doctor with HPR ID '{hpr_id_stripped}' is not verified/active."
            )
        return cached

    # Call the HPR API
    try:
        result = verify_doctor(hpr_id_stripped)
    except AbdmHprDisabledError as exc:
        raise
    except AbdmHprConfigError as exc:
        logger.error("ABDM HPR configuration error: %s", exc)
        raise DoctorVerificationError(f"ABDM HPR configuration error: {exc}") from exc
    except AbdmHprAuthError as exc:
        logger.error("ABDM HPR authentication error: %s", exc)
        raise DoctorVerificationError("ABDM HPR authentication failed.") from exc
    except AbdmHprDoctorNotFoundError as exc:
        logger.warning("Doctor not found in HPR: hpr_id=%s", hpr_id_stripped)
        raise DoctorVerificationError(
            f"Doctor with HPR ID '{hpr_id_stripped}' not found in ABDM registry."
        ) from exc
    except AbdmHprNetworkError as exc:
        logger.error("ABDM HPR network error: %s", exc)
        raise DoctorVerificationError(
            "Unable to connect to ABDM HPR verification service."
        ) from exc
    except AbdmHprServiceError as exc:
        logger.error("ABDM HPR service error: %s", exc)
        raise DoctorVerificationError(
            "ABDM HPR verification service returned an error."
        ) from exc

    # Check verification status
    if not result.get("verified"):
        logger.warning(
            "Doctor not verified in HPR (status=%s): hpr_id=%s",
            result.get("status"),
            hpr_id_stripped,
        )
        _set_cached(hpr_id_stripped, result)
        raise DoctorNotVerifiedError(
            f"Doctor with HPR ID '{hpr_id_stripped}' is not active/verified in ABDM registry "
            f"(status: {result.get('status', 'unknown')})."
        )

    # Cache and return
    _set_cached(hpr_id_stripped, result)
    logger.info(
        "Doctor verified via ABDM HPR: hpr_id=%s, name=%s",
        hpr_id_stripped,
        result.get("name"),
    )
    return result


def verify_doctor_with_fallback(hpr_id: str) -> dict[str, Any] | None:
    """Verify a doctor via ABDM HPR with graceful fallback.

    Unlike `verify_doctor_for_login`, this function never raises
    verification errors. Instead it:
      - Returns the verification result on success
      - Returns None on any failure (network, config, not found, etc.)
      - Logs warnings for all failure paths

    This is useful when ABDM verification should not block login.
    """
    if not settings.abdm_hpr_enabled:
        logger.debug("ABDM HPR is disabled; skipping verification.")
        return None

    try:
        return verify_doctor_for_login(hpr_id)
    except (DoctorVerificationError, DoctorNotVerifiedError) as exc:
        logger.warning("ABDM HPR verification failed (non-blocking): %s", exc)
        return None
    except Exception as exc:
        logger.error("Unexpected error during ABDM HPR verification: %s", exc)
        return None


def is_abdm_hpr_enabled() -> bool:
    """Check whether ABDM HPR integration is enabled."""
    return bool(settings.abdm_hpr_enabled)


def is_abdm_login_enforcement_enabled() -> bool:
    """Check whether ABDM login enforcement is enabled.

    When disabled, doctors can login even if HPR verification fails.
    """
    return bool(settings.abdm_hpr_login_enforcement_enabled)


__all__ = [
    "DoctorNotVerifiedError",
    "DoctorVerificationError",
    "invalidate_hpr_cache",
    "is_abdm_hpr_enabled",
    "is_abdm_login_enforcement_enabled",
    "verify_doctor_for_login",
    "verify_doctor_with_fallback",
]
