from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.config import settings


class DeepSeekReasoningError(Exception):
    pass


class DeepSeekReasoningConfigError(DeepSeekReasoningError):
    pass


class DeepSeekReasoningProcessingError(DeepSeekReasoningError):
    pass


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\\s*|\\s*```$", re.I)


def _parse_json_dict_from_text(raw_text: str) -> dict[str, Any] | None:
    text_value = str(raw_text or "").strip()
    if not text_value:
        return None

    if text_value.startswith("```"):
        text_value = _JSON_FENCE_RE.sub("", text_value).strip()

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


def _prepare_text(value: str, max_chars: int = 60000) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    lines: list[str] = []
    seen: set[str] = set()
    for line in re.split(r"\\r\\n|\\r|\\n", raw):
        t = line.strip()
        if not t:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(t)
    compact = "\\n".join(lines).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars]


def _normalize_decision(value: Any) -> str:
    v = str(value or "").strip().lower()
    if v in {"approve", "approved", "pay", "payable", "yes"}:
        return "approve"
    if v in {"reject", "rejected", "no"}:
        return "reject"
    if v in {
        "query",
        "review",
        "manual_review",
        "manual-review",
        "need_more_evidence",
        "need more evidence",
        "uncertain",
    }:
        return "need_more_evidence"
    return "need_more_evidence"


def _normalize_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if x > 1.0:
        x = x / 100.0
    if x < 0.0:
        x = 0.0
    if x > 1.0:
        x = 1.0
    return float(x)


def _normalize_flags(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    if isinstance(value, list):
        out: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                msg = str(item.get("message") or item.get("flag") or "").strip()
                if msg:
                    out.append({"message": msg, "details": {k: v for k, v in item.items() if k != "message"}})
                continue
            s = str(item or "").strip()
            if s:
                out.append({"message": s, "details": {}})
        return out[:40]
    s = str(value).strip()
    return [{"message": s, "details": {}}] if s else []


def run_deepseek_reasoning(
    normalized_text: str,
    *,
    rule_hits: list[dict[str, Any]] | None = None,
    structured_data: dict[str, Any] | None = None,
    verification_flags: list[dict[str, Any]] | None = None,
    model: str | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    if not settings.deepseek_enabled:
        raise DeepSeekReasoningConfigError("DeepSeek is disabled (DEEPSEEK_ENABLED=false)")
    if not settings.deepseek_api_key:
        raise DeepSeekReasoningConfigError("DEEPSEEK_API_KEY not configured")

    used_model = str(model or settings.deepseek_reasoner_model or "deepseek-reasoner").strip() or "deepseek-reasoner"
    timeout = float(timeout_s or settings.deepseek_timeout_seconds or 60.0)

    text = _prepare_text(normalized_text)
    if not text:
        raise DeepSeekReasoningProcessingError("No normalized claim text available for DeepSeek reasoning")

    rule_hits = rule_hits if isinstance(rule_hits, list) else []
    verification_flags = verification_flags if isinstance(verification_flags, list) else []
    structured_data = structured_data if isinstance(structured_data, dict) else {}

    rule_codes: list[str] = []
    for item in rule_hits:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or item.get("rule_id") or "").strip()
        if code:
            rule_codes.append(code)
        if len(rule_codes) >= 30:
            break

    user_payload = {
        "normalized_text": text,
        "rule_hits": rule_codes,
        "structured_data": {k: v for k, v in structured_data.items() if k not in {"raw_payload"}},
        "verification_flags": verification_flags[:40],
    }

    system_prompt = (
        "You are a medical claim fraud detection AI.\\n"
        "Analyze diagnosis, treatment, investigations, billing, and verification flags.\\n"
        "Return STRICT JSON ONLY with keys: decision, confidence, flags, reason.\\n"
        'decision must be one of: \"approve\", \"reject\", \"need_more_evidence\".\\n'
        "confidence can be 0-1 or 0-100.\\n"
        "Do not invent information. If unclear, choose need_more_evidence.\\n"
    )

    base_url = str(settings.deepseek_base_url or "").strip().rstrip("/")
    if not base_url:
        raise DeepSeekReasoningConfigError("DEEPSEEK_BASE_URL not configured")
    url = f"{base_url}/chat/completions"

    req = {
        "model": used_model,
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    }

    raw_response: dict[str, Any] | None = None
    raw_output = ""
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json=req,
            )
        resp.raise_for_status()
        try:
            raw_response = resp.json()
        except Exception:
            raw_response = {"text": resp.text}

        if isinstance(raw_response, dict):
            choices = raw_response.get("choices")
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message") if isinstance(choices[0], dict) else None
                if isinstance(msg, dict):
                    raw_output = str(msg.get("content") or "").strip()
        if not raw_output and isinstance(raw_response, dict):
            raw_output = str(raw_response.get("output_text") or raw_response.get("content") or "").strip()
    except httpx.HTTPStatusError as exc:
        status = getattr(exc.response, "status_code", None)
        body = ""
        try:
            body = exc.response.text
        except Exception:
            body = ""
        raise DeepSeekReasoningProcessingError(f"DeepSeek HTTP {status}: {body[:400]}") from exc
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise DeepSeekReasoningProcessingError(f"DeepSeek request failed: {exc}") from exc
    except Exception as exc:
        raise DeepSeekReasoningProcessingError(f"DeepSeek reasoning failed: {exc}") from exc

    parsed = _parse_json_dict_from_text(raw_output)
    if not isinstance(parsed, dict):
        raise DeepSeekReasoningProcessingError("DeepSeek returned invalid JSON output")

    return {
        "decision": _normalize_decision(parsed.get("decision")),
        "confidence": _normalize_confidence(parsed.get("confidence")),
        "flags": _normalize_flags(parsed.get("flags")),
        "reason": str(parsed.get("reason") or "").strip(),
        "used_model": used_model,
        "raw_output": raw_output,
        "raw_response": raw_response,
    }


__all__ = [
    "DeepSeekReasoningError",
    "DeepSeekReasoningConfigError",
    "DeepSeekReasoningProcessingError",
    "run_deepseek_reasoning",
]

