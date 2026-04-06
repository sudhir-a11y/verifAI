from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class IfscVerificationDisabledError(RuntimeError):
    pass


class IfscNotFoundError(RuntimeError):
    pass


class IfscNetworkError(RuntimeError):
    pass


class IfscServiceError(RuntimeError):
    pass


def fetch_ifsc_payload(ifsc_code: str) -> dict[str, Any]:
    if not settings.razorpay_ifsc_verify_enabled:
        raise IfscVerificationDisabledError("IFSC verification is disabled.")

    normalized = str(ifsc_code or "").strip()
    base_url = str(settings.razorpay_ifsc_api_base_url or "https://ifsc.razorpay.com").strip().rstrip("/")
    target_url = f"{base_url}/{normalized}"
    timeout_sec = float(settings.razorpay_ifsc_timeout_seconds or 8.0)

    try:
        with httpx.Client(timeout=timeout_sec, follow_redirects=True) as client:
            response = client.get(target_url, headers={"Accept": "application/json"})
    except httpx.RequestError as exc:
        raise IfscNetworkError("Unable to reach IFSC verification service.") from exc

    if response.status_code == 404:
        raise IfscNotFoundError("IFSC not found.")
    if response.status_code >= 400:
        raise IfscServiceError("IFSC verification service error.")

    try:
        payload = response.json()
    except Exception as exc:
        raise IfscServiceError("Invalid response from IFSC verification service.") from exc

    return payload if isinstance(payload, dict) else {}


__all__ = [
    "IfscNetworkError",
    "IfscNotFoundError",
    "IfscServiceError",
    "IfscVerificationDisabledError",
    "fetch_ifsc_payload",
]

