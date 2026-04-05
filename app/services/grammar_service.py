from __future__ import annotations

import json
import re
import threading
from typing import Any


from app.core.config import settings
from app.services.llm_service import (
    LLMServiceError,
    call_openai_chat_completion,
    parse_json_dict_from_text,
)

try:
    import language_tool_python
except Exception:  # pragma: no cover - optional dependency
    language_tool_python = None


class GrammarCheckError(Exception):
    pass


_LANGUAGE_TOOL_LOCK = threading.Lock()
_LANGUAGE_TOOL_INSTANCE: Any | None = None
_LANGUAGE_TOOL_PROVIDER = ""



def _normalize_model_name(raw_model: str | None) -> str:
    configured_model_raw = str(raw_model or "").strip()
    configured_model = configured_model_raw.replace("_", ".") if configured_model_raw else "gpt-4o-mini"
    return configured_model


def _split_html_tokens(report_html: str) -> list[str]:
    text = str(report_html or "")
    return re.split(r"(<[^>]+>)", text)


def _text_segment_indexes(tokens: list[str]) -> list[int]:
    indexes: list[int] = []
    for idx, token in enumerate(tokens):
        if token.startswith("<") and token.endswith(">"):
            continue
        stripped = token.strip()
        if not stripped:
            continue
        if not re.search(r"[A-Za-z]", stripped):
            continue
        indexes.append(idx)
    return indexes


def _preserve_boundary_whitespace(original: str, corrected: str) -> str:
    orig = str(original or "")
    cand = str(corrected or "")
    if not orig:
        return cand

    leading = re.match(r"^\s*", orig)
    trailing = re.search(r"\s*$", orig)
    lead = leading.group(0) if leading else ""
    tail = trailing.group(0) if trailing else ""

    core = cand.strip()
    if not core:
        core = orig.strip()
    return f"{lead}{core}{tail}"


def _reset_language_tool_instance() -> None:
    global _LANGUAGE_TOOL_INSTANCE, _LANGUAGE_TOOL_PROVIDER
    with _LANGUAGE_TOOL_LOCK:
        tool = _LANGUAGE_TOOL_INSTANCE
        _LANGUAGE_TOOL_INSTANCE = None
        _LANGUAGE_TOOL_PROVIDER = ""
    try:
        if tool is not None:
            tool.close()
    except Exception:
        pass


def _get_language_tool_instance() -> tuple[Any, str]:
    if language_tool_python is None:
        raise GrammarCheckError("language_tool_python not installed")

    with _LANGUAGE_TOOL_LOCK:
        if _LANGUAGE_TOOL_INSTANCE is not None:
            return _LANGUAGE_TOOL_INSTANCE, (_LANGUAGE_TOOL_PROVIDER or "local")

        errors: list[str] = []

        try:
            tool = language_tool_python.LanguageTool("en-US")
            globals()["_LANGUAGE_TOOL_INSTANCE"] = tool
            globals()["_LANGUAGE_TOOL_PROVIDER"] = "local"
            return tool, "local"
        except Exception as exc:
            errors.append(f"local: {exc}")

        try:
            tool = language_tool_python.LanguageToolPublicAPI("en-US")
            globals()["_LANGUAGE_TOOL_INSTANCE"] = tool
            globals()["_LANGUAGE_TOOL_PROVIDER"] = "public"
            return tool, "public"
        except Exception as exc:
            errors.append(f"public: {exc}")

    raise GrammarCheckError(f"language_tool failed: {errors[:2] or ['unknown']}")


def _run_grammar_batch_language_tool(segments: list[str]) -> tuple[list[str], str]:
    if not segments:
        return [], "language_tool_python"

    try:
        tool, provider = _get_language_tool_instance()
        corrected: list[str] = []
        for item in segments:
            corrected.append(str(tool.correct(str(item or ""))))
        return corrected, f"language_tool_python:{provider}"
    except Exception as exc:
        # Reset cached instance if it became unhealthy.
        _reset_language_tool_instance()
        raise GrammarCheckError(str(exc)) from exc


def _run_grammar_batch_openai(segments: list[str]) -> tuple[list[str], str]:
    if not settings.openai_api_key:
        raise GrammarCheckError("OPENAI_API_KEY not configured")

    if not segments:
        return [], ""

    prompt = (
        "You are a medical-report grammar checker. "
        "Fix grammar, punctuation, and sentence flow only. "
        "Do not change medical facts, drug names, values, dates, dosages, abbreviations, ICD text, or legal decision wording. "
        "Return strict JSON with same number of segments.\n\n"
        + json.dumps({"segments": segments}, ensure_ascii=False)
    )

    model_candidates = [
        _normalize_model_name(settings.openai_model),
        "gpt-4o-mini",
        "gpt-4.1-mini",
        "gpt-4o",
    ]

    errors: list[str] = []
    for candidate in model_candidates:
        c = str(candidate or "").strip()
        if not c:
            continue
        try:
            result = call_openai_chat_completion(
                model=c,
                system_prompt="Return strict JSON only.",
                user_prompt=prompt,
                timeout_seconds=90.0,
                response_format_json=True,
            )
            parsed = parse_json_dict_from_text(result.output_text)
            if not isinstance(parsed, dict):
                errors.append(f"{c}: invalid_json")
                continue
            corrected = parsed.get("segments")
            if not isinstance(corrected, list) or len(corrected) != len(segments):
                errors.append(f"{c}: invalid_segments")
                continue
            return [str(x or "") for x in corrected], result.used_model
        except LLMServiceError as exc:
            errors.append(f"{c}: {exc}")
        except Exception as exc:
            errors.append(f"{c}: {exc}")

    preview_errors = errors[:3] or ["unknown"]
    raise GrammarCheckError(f"Grammar check failed. models_tried={model_candidates}; errors={preview_errors}")

def grammar_check_report_html(report_html: str) -> dict[str, Any]:
    html = str(report_html or "")
    if not html.strip():
        raise GrammarCheckError("report_html is empty")

    tokens = _split_html_tokens(html)
    segment_idx = _text_segment_indexes(tokens)
    if not segment_idx:
        return {
            "corrected_html": html,
            "changed": False,
            "checked_segments": 0,
            "corrected_segments": 0,
            "model": "",
            "notes": "No editable text segments found.",
        }

    # Chunk segments to keep payloads reliable.
    max_segments_per_batch = 40
    max_chars_per_batch = 9000

    changed = 0
    checked = 0
    used_models: list[str] = []
    provider_used = ""

    cursor = 0
    while cursor < len(segment_idx):
        batch_indexes: list[int] = []
        batch_segments: list[str] = []
        chars = 0

        while cursor < len(segment_idx) and len(batch_indexes) < max_segments_per_batch:
            tok_idx = segment_idx[cursor]
            candidate = str(tokens[tok_idx] or "")
            next_chars = chars + len(candidate)
            if batch_indexes and next_chars > max_chars_per_batch:
                break
            batch_indexes.append(tok_idx)
            batch_segments.append(candidate)
            chars = next_chars
            cursor += 1

        batch_errors: list[str] = []
        corrected_segments: list[str] | None = None
        used_model = ""

        # Free checker first; OpenAI fallback only when free checker is unavailable/fails.
        try:
            corrected_segments, used_model = _run_grammar_batch_language_tool(batch_segments)
            provider_used = "language_tool_python"
        except GrammarCheckError as exc:
            batch_errors.append(str(exc))
            try:
                corrected_segments, used_model = _run_grammar_batch_openai(batch_segments)
                provider_used = "openai"
            except GrammarCheckError as exc2:
                batch_errors.append(str(exc2))
                raise GrammarCheckError(
                    "Grammar check failed with both language_tool and openai. "
                    f"errors={batch_errors[:3]}"
                ) from exc2

        if corrected_segments is None:
            raise GrammarCheckError("Grammar check returned no corrected segments")

        if used_model:
            used_models.append(used_model)

        for local_idx, tok_idx in enumerate(batch_indexes):
            original = str(tokens[tok_idx] or "")
            corrected = _preserve_boundary_whitespace(original, corrected_segments[local_idx])
            checked += 1
            if corrected != original:
                changed += 1
                tokens[tok_idx] = corrected

    corrected_html = "".join(tokens)
    primary_model = used_models[0] if used_models else ""

    return {
        "corrected_html": corrected_html,
        "changed": bool(changed > 0),
        "checked_segments": checked,
        "corrected_segments": changed,
        "model": primary_model,
        "notes": f"Grammar check completed using {provider_used or 'unknown'}.",
    }

