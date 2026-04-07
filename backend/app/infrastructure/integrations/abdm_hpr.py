"""ABDM Healthcare Professionals Registry (HPR) API client.

Handles authentication, doctor lookup, and verification via external HPR APIs.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# Custom exceptions
# ────────────────────────────────────────────────────────────────────

class AbdmHprConfigError(RuntimeError):
    """Raised when ABDM HPR configuration is missing or invalid."""
    pass


class AbdmHprAuthError(RuntimeError):
    """Raised when authentication to ABDM HPR fails."""
    pass


class AbdmHprNetworkError(RuntimeError):
    """Raised when a network error occurs communicating with ABDM HPR."""
    pass


class AbdmHprServiceError(RuntimeError):
    """Raised when ABDM HPR returns an unexpected error response."""
    pass


class AbdmHprDoctorNotFoundError(RuntimeError):
    """Raised when the doctor is not found in the HPR registry."""
    pass


class AbdmHprDisabledError(RuntimeError):
    """Raised when ABDM HPR integration is disabled."""
    pass


# ────────────────────────────────────────────────────────────────────
# Token management (thread-safe, TTL-based)
# ────────────────────────────────────────────────────────────────────

class _TokenManager:
    """Manages ABDM HPR access token with TTL-based caching."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._token: str | None = None
        self._expires_at: float = 0.0

    def get_token(self) -> str:
        """Return a valid token, refreshing if necessary."""
        with self._lock:
            if self._token and time.time() < self._expires_at:
                return self._token
            self._refresh_token()
            return self._token

    def _refresh_token(self) -> None:
        """Request a new access token from ABDM HPR auth endpoint."""
        if not settings.abdm_hpr_enabled:
            raise AbdmHprDisabledError("ABDM HPR integration is disabled.")

        if not settings.abdm_hpr_auth_token_url:
            raise AbdmHprConfigError("ABDM_HPR_AUTH_TOKEN_URL is not configured.")
        if not settings.abdm_hpr_client_id:
            raise AbdmHprConfigError("ABDM_HPR_CLIENT_ID is not configured.")
        if not settings.abdm_hpr_client_secret:
            raise AbdmHprConfigError("ABDM_HPR_CLIENT_SECRET is not configured.")

        timeout = float(settings.abdm_hpr_timeout_seconds or 10.0)

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    settings.abdm_hpr_auth_token_url,
                    data={
                        "client_id": settings.abdm_hpr_client_id,
                        "client_secret": settings.abdm_hpr_client_secret,
                        "grant_type": "client_credentials",
                    },
                )
        except httpx.RequestError as exc:
            logger.error("ABDM HPR token request failed: %s", exc)
            raise AbdmHprNetworkError("Unable to reach ABDM HPR authentication service.") from exc

        if response.status_code != 200:
            logger.error(
                "ABDM HPR auth returned status %d: %s",
                response.status_code,
                response.text[:500],
            )
            raise AbdmHprAuthError("Failed to authenticate with ABDM HPR.")

        try:
            payload = response.json()
        except Exception as exc:
            raise AbdmHprServiceError("Invalid JSON from ABDM HPR auth endpoint.") from exc

        access_token = payload.get("access_token")
        if not access_token:
            raise AbdmHprServiceError("No access_token in ABDM HPR auth response.")

        self._token = access_token
        ttl = int(settings.abdm_hpr_token_ttl_seconds or 300)
        self._expires_at = time.time() + ttl - 10  # 10s safety margin
        logger.info("ABDM HPR access token refreshed (TTL=%ds).", ttl)


_token_manager = _TokenManager()


# ────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────

def _build_headers(extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    """Build request headers with ABDM HPR authorization."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    token = _token_manager.get_token()
    headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    return headers


def fetch_doctor_by_hpr_id(hpr_id: str) -> dict[str, Any]:
    """Fetch doctor details from HPR registry by HPR ID.

    Returns the parsed JSON payload from the HPR API.
    Raises AbdmHprDoctorNotFoundError if the doctor does not exist.
    """
    if not settings.abdm_hpr_enabled:
        raise AbdmHprDisabledError("ABDM HPR integration is disabled.")

    if not settings.abdm_hpr_base_url:
        raise AbdmHprConfigError("ABDM_HPR_BASE_URL is not configured.")

    normalized_hpr_id = str(hpr_id or "").strip()
    if not normalized_hpr_id:
        raise ValueError("hpr_id must not be empty.")

    base = settings.abdm_hpr_base_url.rstrip("/")
    url = f"{base}/v1/health-professionals/{normalized_hpr_id}"
    timeout = float(settings.abdm_hpr_timeout_seconds or 10.0)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, headers=_build_headers())
    except httpx.RequestError as exc:
        logger.error("ABDM HPR doctor lookup failed for hpr_id=%s: %s", normalized_hpr_id, exc)
        raise AbdmHprNetworkError("Unable to reach ABDM HPR service.") from exc

    if response.status_code == 404:
        raise AbdmHprDoctorNotFoundError(
            f"Doctor with HPR ID '{normalized_hpr_id}' not found in registry."
        )
    if response.status_code >= 400:
        logger.error(
            "ABDM HPR returned status %d for hpr_id=%s: %s",
            response.status_code,
            normalized_hpr_id,
            response.text[:500],
        )
        raise AbdmHprServiceError("ABDM HPR service returned an error.")

    try:
        payload = response.json()
    except Exception as exc:
        raise AbdmHprServiceError("Invalid JSON from ABDM HPR service.") from exc

    return payload if isinstance(payload, dict) else {}


def search_doctor_by_registration_number(registration_number: str) -> list[dict[str, Any]]:
    """Search for doctors in HPR registry by registration number.

    Returns a list of matching doctor payloads (may be empty).
    """
    if not settings.abdm_hpr_enabled:
        raise AbdmHprDisabledError("ABDM HPR integration is disabled.")

    if not settings.abdm_hpr_base_url:
        raise AbdmHprConfigError("ABDM_HPR_BASE_URL is not configured.")

    normalized_reg = str(registration_number or "").strip()
    if not normalized_reg:
        raise ValueError("registration_number must not be empty.")

    base = settings.abdm_hpr_base_url.rstrip("/")
    url = f"{base}/v1/health-professionals"
    timeout = float(settings.abdm_hpr_timeout_seconds or 10.0)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(
                url,
                headers=_build_headers(),
                params={"registrationNumber": normalized_reg},
            )
    except httpx.RequestError as exc:
        logger.error(
            "ABDM HPR doctor search failed for reg=%s: %s", normalized_reg, exc
        )
        raise AbdmHprNetworkError("Unable to reach ABDM HPR service.") from exc

    if response.status_code >= 400:
        logger.error(
            "ABDM HPR search returned status %d for reg=%s: %s",
            response.status_code,
            normalized_reg,
            response.text[:500],
        )
        raise AbdmHprServiceError("ABDM HPR search service returned an error.")

    try:
        payload = response.json()
    except Exception as exc:
        raise AbdmHprServiceError("Invalid JSON from ABDM HPR search service.") from exc

    # The response may be a list or a dict with a nested list
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        # Common patterns: {"results": [...]}, {"data": [...]}, {"professionals: [...]}
        for key in ("results", "data", "professionals", "healthProfessionals"):
            if key in payload and isinstance(payload[key], list):
                return payload[key]
        return [payload]  # single object fallback
    return []


def verify_doctor(hpr_id: str) -> dict[str, Any]:
    """Verify a doctor's registration status via HPR.

    Returns a normalized verification result dict with keys:
      - hpr_id: str
      - name: str
      - registration_number: str
      - status: str (e.g. "Active", "Inactive", "Suspended")
      - qualifications: list[str]
      - speciality: str | None
      - verified: bool (True if status is active)
    """
    raw = fetch_doctor_by_hpr_id(hpr_id)

    # Extract fields with defensive defaults
    # The actual ABDM response structure may vary; we handle common patterns.
    name = (
        raw.get("name")
        or raw.get("fullName")
        or raw.get("doctorName")
        or raw.get("practitionerName", "")
    )
    registration_number = (
        raw.get("registrationNumber")
        or raw.get("registrationNo")
        or raw.get("regNumber", "")
    )
    status = raw.get("status") or raw.get("registrationStatus") or "Unknown"
    qualifications = raw.get("qualifications") or raw.get("degrees") or []
    speciality = raw.get("speciality") or raw.get("specialization")

    if isinstance(qualifications, str):
        qualifications = [qualifications]
    if not isinstance(qualifications, list):
        qualifications = []

    verified = str(status).lower() in ("active", "verified", "registered", "valid")

    return {
        "hpr_id": hpr_id,
        "name": str(name),
        "registration_number": str(registration_number),
        "status": str(status),
        "qualifications": qualifications,
        "speciality": str(speciality) if speciality else None,
        "verified": verified,
        "raw": raw,
    }


__all__ = [
    "AbdmHprConfigError",
    "AbdmHprAuthError",
    "AbdmHprDisabledError",
    "AbdmHprDoctorNotFoundError",
    "AbdmHprNetworkError",
    "AbdmHprServiceError",
    "fetch_doctor_by_hpr_id",
    "search_doctor_by_registration_number",
    "verify_doctor",
]
