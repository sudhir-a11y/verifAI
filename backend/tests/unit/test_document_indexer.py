from app.ai.document_indexer import build_index, chunk_pages, embed_chunks, search


def test_chunk_pages_splits_text() -> None:
    pages = [{"page": 1, "text": "A " * 5000}]
    chunks = chunk_pages(pages, max_chars=500, overlap_chars=50)
    assert len(chunks) > 3
    assert all("chunk_id" in c and "page" in c and "text" in c for c in chunks)


def test_embed_and_search_local_provider() -> None:
    pages = [
        {"page": 1, "text": "Admission notes. Diagnosis: Sepsis. Treatment started."},
        {"page": 2, "text": "Discharge summary. Diagnosis: Viral fever."},
    ]
    idx = build_index(pages, provider="local")
    hits = search("sepsis diagnosis", {"chunks": [c.__dict__ for c in idx.chunks], "embeddings": idx.embeddings, "embedding_provider": "local"})
    assert hits
    # Local embedding is deterministic but approximate; ensure the relevant page is surfaced.
    assert any(h["page"] == 1 for h in hits[:2])

    # Also exercise embed_chunks() directly (local)
    chunks = chunk_pages(pages)
    embedded = embed_chunks(chunks, provider="local")
    assert embedded and isinstance(embedded[0].get("embedding"), list)
