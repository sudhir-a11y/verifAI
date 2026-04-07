from app.ai.document_analyzer import analyze_hits


def test_analyze_hits_heuristic() -> None:
    hits_by_query = {
        "what is diagnosis": [{"chunk_id": "p1-c0", "page": 1, "score": 0.9, "text": "Diagnosis: Sepsis"}],
        "what is claim amount": [],
    }
    out = analyze_hits(hits_by_query, queries=["what is diagnosis", "what is claim amount"], use_ai=False)
    assert out["severity"] in {"low", "medium", "high"}
    assert "flags" in out
    assert any(f.get("code") == "MISSING_EVIDENCE" for f in out.get("flags", []))

