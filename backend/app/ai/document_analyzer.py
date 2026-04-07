from __future__ import annotations

"""
Document Analyzer — automatic analysis on top of DocumentIndexer.

This module is NOT a chatbot. It:
  - builds/searches an index over OCR pages
  - retrieves relevant chunks for a small set of queries
  - (optionally) uses an LLM to produce strict JSON with summary + flags
  - falls back to a deterministic heuristic output when LLM is unavailable
"""

import json
from pathlib import Path
from typing import Any

from app.ai.document_indexer import DocumentIndex, build_index
from app.ai.openai_responses import OpenAIResponsesError, extract_responses_text, responses_create
from app.core.config import settings


DEFAULT_QUERIES = [
    "what is diagnosis",
    "what is hospital name",
    "who is treating doctor",
    "what is date of admission",
    "what is date of discharge",
    "what medicines were used",
    "what is claim amount",
]


def analyze_pages(
    pages: list[dict[str, Any]],
    *,
    queries: list[str] | None = None,
    top_k_per_query: int = 5,
    embedding_provider: str = "auto",
    use_ai: bool = True,
) -> dict[str, Any]:
    """
    Analyze OCR pages and return structured analysis (summary + flags + evidence).

    If `use_ai` is True and `OPENAI_API_KEY` is configured, uses a strict-json prompt.
    Otherwise returns a simple deterministic heuristic output.
    """
    query_list = [str(q).strip() for q in (queries or DEFAULT_QUERIES) if str(q).strip()]
    idx = build_index(pages, provider=embedding_provider)
    hits_by_query: dict[str, list[dict[str, Any]]] = {}
    for q in query_list:
        hits_by_query[q] = [h.__dict__ for h in idx.search(q, top_k=top_k_per_query)]

    if use_ai and settings.openai_api_key:
        try:
            return _analyze_with_llm(hits_by_query, queries=query_list)
        except Exception:
            # Always fall back to heuristic output (never crash callers).
            return _analyze_heuristic(hits_by_query, queries=query_list)

    return _analyze_heuristic(hits_by_query, queries=query_list)


def analyze_hits(
    hits_by_query: dict[str, list[dict[str, Any]]],
    *,
    queries: list[str],
    use_ai: bool = True,
) -> dict[str, Any]:
    """Analyze already-retrieved hits (no re-indexing)."""
    query_list = [str(q).strip() for q in (queries or []) if str(q).strip()]
    if not query_list:
        query_list = DEFAULT_QUERIES
    if use_ai and settings.openai_api_key:
        try:
            return _analyze_with_llm(hits_by_query, queries=query_list)
        except Exception:
            return _analyze_heuristic(hits_by_query, queries=query_list)
    return _analyze_heuristic(hits_by_query, queries=query_list)


def _analyze_with_llm(hits_by_query: dict[str, list[dict[str, Any]]], *, queries: list[str]) -> dict[str, Any]:
    model = str(settings.openai_rag_model or settings.openai_model or "gpt-4o-mini").strip() or "gpt-4o-mini"
    prompt_text = _load_prompt_text()

    payload_obj = {"queries": queries, "hits_by_query": hits_by_query}
    user_text = prompt_text.strip() + "\n\nINPUT JSON:\n" + json.dumps(payload_obj, ensure_ascii=False)

    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": "Return strict JSON only."}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_text}]},
        ],
    }

    try:
        body = responses_create(payload, timeout_s=60.0)
    except OpenAIResponsesError as exc:
        raise RuntimeError(f"LLM analysis failed: HTTP {exc.status_code or 'unknown'}: {exc}") from exc

    text_out = extract_responses_text(body)
    parsed = _parse_json_obj(text_out)
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM output was not valid JSON object")

    # Minimal validation + normalization
    parsed.setdefault("summary", {})
    parsed.setdefault("flags", [])
    parsed.setdefault("severity", "low")
    parsed.setdefault("recommendation", "need_more_evidence")
    parsed.setdefault("confidence", 0.0)
    return parsed


def _analyze_heuristic(hits_by_query: dict[str, list[dict[str, Any]]], *, queries: list[str]) -> dict[str, Any]:
    # Heuristic: if any query returns 0 hits, flag as missing evidence.
    flags: list[dict[str, Any]] = []
    for q in queries:
        hits = hits_by_query.get(q) or []
        if not hits:
            flags.append(
                {
                    "code": "MISSING_EVIDENCE",
                    "severity": "medium",
                    "message": f"No relevant text found for query: '{q}'",
                    "evidence": [],
                }
            )

    severity = "low"
    if any(f.get("severity") == "high" for f in flags):
        severity = "high"
    elif flags:
        severity = "medium"

    recommendation = "approve" if severity == "low" else "need_more_evidence"
    confidence = 0.85 if severity == "low" else 0.55

    return {
        "summary": {
            "diagnosis": "",
            "hospital_name": "",
            "treating_doctor": "",
            "doa": "",
            "dod": "",
            "claim_amount": "",
            "medicines_used": [],
        },
        "flags": flags,
        "severity": severity,
        "recommendation": recommendation,
        "confidence": float(confidence),
        "hits_by_query": hits_by_query,
    }


def _load_prompt_text() -> str:
    # Keep prompt in repo root `prompts/` folder (human-editable).
    repo_root = Path(__file__).resolve().parents[3]
    path = repo_root / "prompts" / "document_analyzer_prompt.md"
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        # Safe fallback
        return (
            "You are an automatic document analysis engine. Return strict JSON only.\n"
            "Extract diagnosis, hospital_name, treating_doctor, doa, dod, claim_amount, medicines_used.\n"
            "Create flags with evidence quotes from provided chunks.\n"
        )


def _parse_json_obj(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        # Try to salvage a JSON object substring.
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                obj = json.loads(raw[start : end + 1])
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None
        return None


__all__ = ["analyze_pages", "analyze_hits", "DEFAULT_QUERIES", "DocumentIndex"]
