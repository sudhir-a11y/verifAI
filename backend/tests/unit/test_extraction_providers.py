import pytest


def test_openai_provider_falls_back_to_local_when_api_key_missing(monkeypatch):
    from app.ai.extraction.providers import run_extraction
    from app.core.config import settings
    from app.schemas.extraction import ExtractionProvider

    monkeypatch.setattr(settings, "openai_api_key", None, raising=False)

    result = run_extraction(
        provider=ExtractionProvider.openai,
        document_name="sample.txt",
        mime_type="text/plain",
        payload=b"Claim ID: ABC-123\nPatient Name: John Doe\nDiagnosis: test",
    )

    assert result["provider"] == ExtractionProvider.local.value
    assert isinstance(result.get("raw_response"), dict)
    assert result["raw_response"]["openai_fallback"]["reason"] == "missing_api_key"

