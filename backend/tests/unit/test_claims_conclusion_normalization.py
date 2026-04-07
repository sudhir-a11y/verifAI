from app.ai.claims_conclusion import _normalize_ai_conclusion_paragraph


def test_normalize_enforces_verdict_even_if_allowed_ending_present() -> None:
    raw = (
        "Treatment is not justified and evidence is missing. Therefore, the claim is admissible."
    )
    out = _normalize_ai_conclusion_paragraph(raw, "reject")
    assert out.endswith("Therefore, the claim is recommended for rejection.")
    assert "Therefore, the claim is admissible." not in out


def test_normalize_removes_multiple_verdicts_and_appends_one() -> None:
    raw = (
        "Unsupported. Therefore, the claim is kept under query. Also note issues. "
        "Therefore, the claim is admissible."
    )
    out = _normalize_ai_conclusion_paragraph(raw, "query")
    assert out.count("Therefore, the claim is") == 1
    assert out.endswith("Therefore, the claim is kept under query.")

