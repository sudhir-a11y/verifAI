from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


def fetch_teamrightworks_sync_payload(params: dict[str, Any]) -> dict[str, Any]:
    sync_url = str(settings.teamrightworks_sync_trigger_url or "").strip()
    sync_key = str(settings.teamrightworks_sync_trigger_key or "").strip()
    if not sync_url:
        raise RuntimeError("TEAMRIGHTWORKS_SYNC_TRIGGER_URL is not configured")
    if not sync_key:
        raise RuntimeError("TEAMRIGHTWORKS_SYNC_TRIGGER_KEY is not configured")

    full_params: dict[str, Any] = {"key": sync_key}
    full_params.update(params)

    with httpx.Client(timeout=httpx.Timeout(180.0, connect=20.0), follow_redirects=True) as client:
        response = client.get(sync_url, params=full_params)

    body_text = response.text or ""
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"legacy sync returned non-JSON (HTTP {response.status_code})") from exc

    if response.status_code >= 400:
        detail = payload.get("error") if isinstance(payload, dict) else None
        detail_text = str(detail or body_text[:250] or f"HTTP {response.status_code}")
        raise RuntimeError(f"legacy sync failed: {detail_text}")

    if not isinstance(payload, dict):
        raise RuntimeError("legacy sync returned invalid payload")

    return payload

