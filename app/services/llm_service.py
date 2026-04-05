from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings


class LLMServiceError(Exception):
    pass


class LLMRateLimitError(LLMServiceError):
    pass


@dataclass
class OpenAIChatResult:
    used_model: str
    body: dict[str, Any]
    output_text: str


def normalize_model_candidates(candidates: list[str | None]) -> list[str]:
    normalized: list[str] = []
    for item in candidates:
        model = str(item or "").strip()
        if model and model not in normalized:
            normalized.append(model)
    return normalized


def extract_openai_response_text(body: Any) -> str:
    if not isinstance(body, dict):
        return ""

    direct = body.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    output_chunks: list[str] = []
    output = body.get("output")
    if isinstance(output, list):
        for out in output:
            if not isinstance(out, dict):
                continue
            content = out.get("content")
            if not isinstance(content, list):
                continue
            for item in content:
                if not isinstance(item, dict):
                    continue
                t = item.get("text") or item.get("content")
                if isinstance(t, str) and t.strip():
                    output_chunks.append(t.strip())
        if output_chunks:
            return "\n".join(output_chunks).strip()

    msg = (((body.get("choices") or [{}])[0]).get("message") or {}) if isinstance(body.get("choices"), list) else {}
    msg_content = msg.get("content") if isinstance(msg, dict) else ""
    if isinstance(msg_content, str):
        return msg_content.strip()
    if isinstance(msg_content, list):
        joined: list[str] = []
        for item in msg_content:
            if isinstance(item, dict):
                t = item.get("text") or item.get("content")
                if isinstance(t, str) and t.strip():
                    joined.append(t.strip())
        return "\n".join(joined).strip()
    return ""


def parse_json_dict_from_text(raw_text: str) -> dict[str, Any] | None:
    text_value = str(raw_text or "").strip()
    if not text_value:
        return None

    if text_value.startswith("```"):
        text_value = re.sub(r"^```(?:json)?\s*", "", text_value, flags=re.I)
        text_value = re.sub(r"\s*```$", "", text_value)
        text_value = text_value.strip()

    try:
        parsed = json.loads(text_value)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    first = text_value.find("{")
    last = text_value.rfind("}")
    if first >= 0 and last > first:
        candidate = text_value[first : last + 1]
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _chat_completion_url() -> str:
    base_url = settings.openai_base_url.rstrip("/") if settings.openai_base_url else "https://api.openai.com/v1"
    return f"{base_url}/chat/completions"


def _headers() -> dict[str, str]:
    if not settings.openai_api_key:
        raise LLMServiceError("OPENAI_API_KEY not configured")
    return {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }


def call_openai_chat_completion(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: float = 120.0,
    response_format_json: bool = False,
    temperature: float | None = None,
) -> OpenAIChatResult:
    model_name = str(model or "").strip()
    if not model_name:
        raise LLMServiceError("model is required")

    request_payload: dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if response_format_json:
        request_payload["response_format"] = {"type": "json_object"}
    if temperature is not None:
        request_payload["temperature"] = float(temperature)

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(_chat_completion_url(), headers=_headers(), json=request_payload)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else 0
        detail = ""
        try:
            detail = (exc.response.text or "")[:800] if exc.response is not None else ""
        except Exception:
            detail = ""
        if status_code == 429:
            raise LLMRateLimitError("OPENAI_RATE_LIMITED") from exc
        raise LLMServiceError(f"HTTP {status_code}: {detail or str(exc)}") from exc
    except Exception as exc:
        raise LLMServiceError(str(exc)) from exc

    body = response.json() if response is not None else {}
    if not isinstance(body, dict):
        body = {}
    used_model = str(body.get("model") or model_name)
    output_text = extract_openai_response_text(body)
    return OpenAIChatResult(used_model=used_model, body=body, output_text=output_text)
