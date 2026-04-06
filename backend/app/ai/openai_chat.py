from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class OpenAIChatError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, response_text: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


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

def extract_message_text(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    choices = body.get("choices") if isinstance(body.get("choices"), list) else []
    first = choices[0] if choices else {}
    message = first.get("message") if isinstance(first, dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        out: list[str] = []
        for item in content:
            if isinstance(item, dict):
                val = item.get("text") or item.get("content")
                if isinstance(val, str) and val.strip():
                    out.append(val.strip())
        return "\n".join(out).strip()
    return ""


def chat_completions(
    messages: list[dict[str, Any]],
    *,
    model: str,
    temperature: float = 0.1,
    timeout_s: float = 120.0,
    extra: dict[str, Any] | None = None,
) -> dict:
    url = f"{_base_url()}/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": float(temperature),
    }
    if extra:
        payload.update(extra)
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
        raise OpenAIChatError(str(exc), status_code=status_code, response_text=text_value) from exc
    except Exception as exc:
        raise OpenAIChatError(str(exc)) from exc
    if not isinstance(body, dict):
        raise OpenAIChatError("unexpected OpenAI response shape")
    return body
