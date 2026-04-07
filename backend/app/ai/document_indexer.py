from __future__ import annotations

"""
DocumentIndexer — minimal OCR text indexing for search.

This module does ONLY 3 things:
  1) chunk OCR text (pages -> chunks)
  2) create embeddings (chunks -> vectors)
  3) search (query -> best chunks)

No pipeline orchestration, no UI, no langgraph.
"""

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any, Iterable

import httpx

from app.core.config import settings


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    page: int
    text: str


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    page: int
    score: float
    text: str


@dataclass
class DocumentIndex:
    chunks: list[Chunk]
    embeddings: list[list[float]]  # aligned with chunks
    embedding_provider: str = "auto"

    def search(self, query: str, *, top_k: int = 5) -> list[SearchHit]:
        q = str(query or "").strip()
        if not q:
            return []
        query_vec = _embed_texts([q], provider=self.embedding_provider)[0]
        scored: list[tuple[float, int]] = []
        for i, vec in enumerate(self.embeddings):
            scored.append((_cosine_similarity(query_vec, vec), i))
        scored.sort(key=lambda t: t[0], reverse=True)
        hits: list[SearchHit] = []
        for score, idx in scored[: max(1, int(top_k or 5))]:
            c = self.chunks[idx]
            hits.append(SearchHit(chunk_id=c.chunk_id, page=c.page, score=float(score), text=c.text))
        return hits


# ---------------------------------------------------------------------------
# Public functions (as required by context/next_update.md)
# ---------------------------------------------------------------------------


def chunk_pages(pages: list[dict[str, Any]], *, max_chars: int = 1200, overlap_chars: int = 200) -> list[dict[str, Any]]:
    """Chunk OCR pages into small text chunks.

    Input:
        [{"page": 1, "text": "..."}, ...]

    Output:
        [{"chunk_id": "...", "page": 1, "text": "..."}, ...]
    """
    max_chars = max(200, int(max_chars or 1200))
    overlap_chars = max(0, min(int(overlap_chars or 0), max_chars - 50))

    def _iter_page_dicts() -> Iterable[tuple[int, str]]:
        for row in pages or []:
            if not isinstance(row, dict):
                continue
            page_no = row.get("page")
            text_value = row.get("text")
            try:
                page_int = int(page_no)
            except Exception:
                continue
            text_str = _normalize_text(text_value)
            if not text_str:
                continue
            yield page_int, text_str

    chunks: list[dict[str, Any]] = []
    for page_int, text_str in sorted(_iter_page_dicts(), key=lambda t: t[0]):
        start = 0
        idx = 0
        while start < len(text_str):
            end = min(len(text_str), start + max_chars)
            # Prefer to break on whitespace near the end
            cut = _find_breakpoint(text_str, start, end)
            piece = text_str[start:cut].strip()
            if piece:
                chunks.append(
                    {
                        "chunk_id": f"p{page_int}-c{idx}",
                        "page": page_int,
                        "text": piece,
                    }
                )
                idx += 1
            if cut >= len(text_str):
                break
            start = max(0, cut - overlap_chars)

    return chunks


def embed_chunks(chunks: list[dict[str, Any]], *, provider: str = "auto") -> list[dict[str, Any]]:
    """Create embeddings for chunks.

    Adds `embedding` key to each chunk dict and returns the updated list.
    """
    texts: list[str] = []
    for c in chunks or []:
        if isinstance(c, dict):
            texts.append(_normalize_text(c.get("text")))
        else:
            texts.append("")

    vectors = _embed_texts(texts, provider=provider)
    out: list[dict[str, Any]] = []
    for c, vec in zip(chunks or [], vectors, strict=False):
        if not isinstance(c, dict):
            continue
        item = dict(c)
        item["embedding"] = vec
        out.append(item)
    return out


def search(query: str, index: dict[str, Any] | DocumentIndex, *, top_k: int = 5) -> list[dict[str, Any]]:
    """Search an index for the most relevant chunks.

    Note: `context/next_update.md` shows `search(query)` but does not specify
    where the index lives. This function accepts either:
      - a `DocumentIndex`
      - a dict containing `chunks` + `embeddings`
    """
    if isinstance(index, DocumentIndex):
        hits = index.search(query, top_k=top_k)
        return [hit.__dict__ for hit in hits]

    chunks_raw = (index or {}).get("chunks") if isinstance(index, dict) else None
    embeds_raw = (index or {}).get("embeddings") if isinstance(index, dict) else None
    provider = (index or {}).get("embedding_provider") if isinstance(index, dict) else "auto"
    chunks_list: list[Chunk] = []
    embeddings_list: list[list[float]] = []

    if isinstance(chunks_raw, list) and isinstance(embeds_raw, list):
        for c in chunks_raw:
            if isinstance(c, Chunk):
                chunks_list.append(c)
            elif isinstance(c, dict):
                chunks_list.append(
                    Chunk(
                        chunk_id=str(c.get("chunk_id") or ""),
                        page=int(c.get("page") or 0),
                        text=str(c.get("text") or ""),
                    )
                )
        for v in embeds_raw:
            if isinstance(v, list):
                embeddings_list.append([float(x) for x in v])

    idx = DocumentIndex(chunks=chunks_list, embeddings=embeddings_list, embedding_provider=str(provider or "auto"))
    hits = idx.search(query, top_k=top_k)
    return [hit.__dict__ for hit in hits]


def build_index(pages: list[dict[str, Any]], *, provider: str = "auto") -> DocumentIndex:
    """Helper to go from raw pages -> ready-to-search index."""
    chunk_dicts = chunk_pages(pages)
    chunks = [Chunk(chunk_id=str(c["chunk_id"]), page=int(c["page"]), text=str(c["text"])) for c in chunk_dicts]
    embeddings = _embed_texts([c.text for c in chunks], provider=provider)
    return DocumentIndex(chunks=chunks, embeddings=embeddings, embedding_provider=provider)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


_WS_RE = re.compile(r"\s+")


def _normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\x00", " ")
    text = _WS_RE.sub(" ", text).strip()
    return text


def _find_breakpoint(text: str, start: int, end: int) -> int:
    if end >= len(text):
        return len(text)
    window = text[start:end]
    # find last whitespace in last 15% of window
    tail_start = max(0, len(window) - max(20, int(len(window) * 0.15)))
    tail = window[tail_start:]
    m = re.search(r"\s(?!.*\s)", tail)
    if m:
        return start + tail_start + m.start()
    return end


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=False):
        dot += float(x) * float(y)
        na += float(x) * float(x)
        nb += float(y) * float(y)
    denom = math.sqrt(na) * math.sqrt(nb)
    if denom <= 0:
        return 0.0
    return float(dot / denom)


def _embed_texts(texts: list[str], *, provider: str = "auto") -> list[list[float]]:
    p = str(provider or "auto").strip().lower()
    if p == "openai" or (p == "auto" and bool(settings.openai_api_key)):
        try:
            return _embed_openai(texts)
        except Exception:
            # Fall back to local deterministic embeddings if OpenAI fails.
            return _embed_local(texts)
    return _embed_local(texts)


def _embed_openai(texts: list[str]) -> list[list[float]]:
    model = str(getattr(settings, "openai_embedding_model", "") or "text-embedding-3-small")
    base_url = settings.openai_base_url.rstrip("/") if settings.openai_base_url else "https://api.openai.com/v1"
    url = f"{base_url}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "input": texts}
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        body = resp.json()
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list):
        raise RuntimeError("Unexpected embeddings response")
    vectors: list[list[float]] = []
    for row in data:
        emb = row.get("embedding") if isinstance(row, dict) else None
        if not isinstance(emb, list):
            raise RuntimeError("Unexpected embedding item")
        vectors.append([float(x) for x in emb])
    return vectors


def _embed_local(texts: list[str], *, dim: int = 128) -> list[list[float]]:
    """Deterministic, no-network embedding (for dev/tests)."""
    out: list[list[float]] = []
    for t in texts:
        tokens = re.findall(r"[a-z0-9]+", str(t or "").lower())
        vec = [0.0] * dim
        for tok in tokens:
            h = hashlib.sha256(tok.encode("utf-8")).digest()
            idx = int.from_bytes(h[:4], "big") % dim
            vec[idx] += 1.0
        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        out.append([v / norm for v in vec])
    return out


__all__ = ["Chunk", "SearchHit", "DocumentIndex", "chunk_pages", "embed_chunks", "search", "build_index"]
