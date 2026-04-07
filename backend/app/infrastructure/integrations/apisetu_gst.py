from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class ApisetuGstDisabledError(RuntimeError):
    pass


class ApisetuGstConfigError(RuntimeError):
    pass


class ApisetuGstNetworkError(RuntimeError):
    pass


class ApisetuGstServiceError(RuntimeError):
    pass


def _build_taxpayer_url(gstin: str) -> str:
    gstin_norm = str(gstin or "").strip().upper()
    if not gstin_norm:
        raise ValueError("gstin must not be empty")

    template = str(settings.apisetu_gst_taxpayer_url_template or "").strip()
    if template:
        return template.format(gstin=gstin_norm)

    base = str(settings.apisetu_gst_base_url or "").strip().rstrip("/")
    if not base:
        raise ApisetuGstConfigError(
            "APISETU_GST_TAXPAYER_URL_TEMPLATE or APISETU_GST_BASE_URL must be configured."
        )

    # We intentionally do not assume a path here; users should supply a template
    # for the exact subscribed API on APISetu.
    raise ApisetuGstConfigError(
        "APISETU_GST_TAXPAYER_URL_TEMPLATE is required to call APISetu Taxpayer API."
    )


def _build_headers() -> dict[str, str]:
    api_key = str(settings.apisetu_api_key or "").strip()
    if not api_key:
        raise ApisetuGstConfigError("APISETU_API_KEY is not configured.")
    header_name = str(settings.apisetu_api_key_header or "x-api-key").strip()
    if not header_name:
        header_name = "x-api-key"

    return {
        "Accept": "application/json",
        header_name: api_key,
    }


def fetch_taxpayer_details(gstin: str) -> dict[str, Any]:
    """Fetch GST taxpayer details via APISetu (Taxpayers API).

    Note: APISetu endpoint paths vary by subscription; configure
    `APISETU_GST_TAXPAYER_URL_TEMPLATE` with `{gstin}`.
    """
    if not settings.apisetu_gst_enabled:
        raise ApisetuGstDisabledError("APISetu GST integration is disabled.")

    url = _build_taxpayer_url(gstin)
    timeout = float(settings.apisetu_gst_timeout_seconds or 10.0)

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers=_build_headers())
    except httpx.RequestError as exc:
        logger.warning("APISetu GST request failed: %s", exc)
        raise ApisetuGstNetworkError("Unable to reach APISetu GST service.") from exc

    if resp.status_code >= 400:
        logger.warning("APISetu GST returned status=%d body=%s", resp.status_code, resp.text[:500])
        raise ApisetuGstServiceError("APISetu GST service returned an error.")

    try:
        payload = resp.json()
    except Exception as exc:
        raise ApisetuGstServiceError("Invalid JSON from APISetu GST service.") from exc

    return payload if isinstance(payload, dict) else {}


__all__ = [
    "ApisetuGstConfigError",
    "ApisetuGstDisabledError",
    "ApisetuGstNetworkError",
    "ApisetuGstServiceError",
    "fetch_taxpayer_details",
]

