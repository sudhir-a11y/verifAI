from app.ai.document_analyzer import analyze_pages


def test_analyze_pages_heuristic_mode() -> None:
    pages = [
        {"page": 1, "text": "Diagnosis: Sepsis. Hospital: City Hospital. DOA: 2026-03-01."},
        {"page": 2, "text": "Discharge on 2026-03-05. Medicines: Meropenem."},
    ]
    out = analyze_pages(pages, use_ai=False, embedding_provider="local")
    assert isinstance(out, dict)
    assert "flags" in out and "severity" in out and "recommendation" in out and "confidence" in out
    assert "hits_by_query" in out

