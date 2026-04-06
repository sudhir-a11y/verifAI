from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class OpenAIChatError(RuntimeError):
    pass


def _base_url() -> str:
    base_url = settings.openai_base_url.rstrip("/") if settings.openai_base_url else "https://api.openai.com/v1"
    return base_url


def _auth_headers() -> dict[str, str]:
    if not settings.openai_api_key:
        raise OpenAIChatError("OPENAI_API_KEY not configured")
    return {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }


def chat_completions(messages: list[dict[str, Any]], *, model: str, temperature: float = 0.1, timeout_s: float = 120.0) -> dict:
    url = f"{_base_url()}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(temperature),
    }
    try:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(url, headers=_auth_headers(), json=payload)
            response.raise_for_status()
        body = response.json()
    except Exception as exc:
        raise OpenAIChatError(str(exc)) from exc
    if not isinstance(body, dict):
        raise OpenAIChatError("unexpected OpenAI response shape")
    return body

