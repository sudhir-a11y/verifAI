from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class OpenAIResponsesError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, response_text: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


def _base_url() -> str:
    base_url = settings.openai_base_url.rstrip("/") if settings.openai_base_url else "https://api.openai.com/v1"
    return base_url


def _auth_headers() -> dict[str, str]:
    if not settings.openai_api_key:
        raise OpenAIResponsesError("OPENAI_API_KEY not configured")
    return {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }


def extract_responses_text(body: Any) -> str:
    """Extract text from OpenAI /responses API output.

    Handles both ``output_text`` (direct string) and ``output[].content[].text`` formats.
    """
    if not isinstance(body, dict):
        return ""

    direct = body.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    out: list[str] = []
    output = body.get("output")
    if isinstance(output, list):
        for row in output:
            if not isinstance(row, dict):
                continue
            content = row.get("content")
            if not isinstance(content, list):
                continue
            for item in content:
                if isinstance(item, dict):
                    t = item.get("text")
                    if isinstance(t, str) and t.strip():
                        out.append(t.strip())
    if out:
        return "\n".join(out).strip()
    return ""


def responses_create(payload: dict[str, Any], *, timeout_s: float = 120.0) -> dict:
    url = f"{_base_url()}/responses"
    try:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(url, headers=_auth_headers(), json=payload)
            response.raise_for_status()
        body = response.json()
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        try:
            text_value = (exc.response.text or "")[:1200] if exc.response is not None else ""
        except Exception:
            text_value = ""
        raise OpenAIResponsesError(str(exc), status_code=status_code, response_text=text_value) from exc
    except Exception as exc:
        raise OpenAIResponsesError(str(exc)) from exc

    if not isinstance(body, dict):
        raise OpenAIResponsesError("unexpected OpenAI response shape")
    return body

