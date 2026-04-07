"""
Unit tests for Phase 1 document structurer (OCR text -> structured JSON).
"""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.ai.document_structurer import structure_document_text


class TestDocumentStructurerRuleBased:
    def test_empty_input(self):
        out = structure_document_text("", use_llm=False)
        assert out["doctor_name"] == ""
        assert out["diagnosis"] == ""
        assert out["medicines"] == []
        assert out["duration"] == ""
        assert out["hospital"] == ""
        assert out["date"] == ""

    def test_example_structuring(self):
        text = "Tab PCM 650\nDr Sharma\nViral fever\n3 days\n"
        out = structure_document_text(text, use_llm=False)
        assert "sharma" in out["doctor_name"].lower()
        assert "viral" in out["diagnosis"].lower()
        assert out["duration"] == "3 days"
        assert any("pcm" in m.lower() for m in out["medicines"])

    def test_date_normalization(self):
        text = "Dr Sharma\nDate: 07/04/2026\nViral fever\n"
        out = structure_document_text(text, use_llm=False)
        assert out["date"] == "2026-04-07"

