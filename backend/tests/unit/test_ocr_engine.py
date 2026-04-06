"""
Unit tests for Hybrid OCR Engine module (Phase 0).
Tests: OCRResult, provider functions, routing, error handling.
"""

import pytest
from pathlib import Path
from PIL import Image
import time

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.fixtures.helpers import (
    create_sample_image,
    create_prescription_image,
)
from app.ai.page_classifier import PageType
from app.ai.ocr_engine import (
    OCRResult,
    OCRError,
    OCRConfigError,
    OCRProcessingError,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def sample_image():
    """Create a sample image for testing."""
    return create_sample_image("Test prescription text")


@pytest.fixture
def prescription_img():
    """Create a prescription image."""
    return create_prescription_image()


# ─── Tests: OCRResult Class ────────────────────────────────────────────────

class TestOCRResult:
    """Tests for OCRResult class."""

    def test_basic_creation(self):
        """Should create OCRResult with basic parameters."""
        result = OCRResult(
            text="Test text",
            confidence=0.85,
            provider="test_provider",
            processing_time=1.5,
        )
        assert result.text == "Test text"
        assert result.confidence == 0.85
        assert result.provider == "test_provider"
        assert result.processing_time == 1.5

    def test_with_optional_params(self):
        """Should handle optional parameters."""
        result = OCRResult(
            text="Test text",
            confidence=0.9,
            provider="paddle",
            processing_time=2.0,
            page_type="prescription",
            bounding_boxes=[{"text": "word", "box": [0, 0, 10, 10]}],
            metadata={"key": "value"},
        )
        assert result.page_type == "prescription"
        assert len(result.bounding_boxes) == 1
        assert result.metadata == {"key": "value"}

    def test_to_dict(self):
        """Should convert result to dictionary correctly."""
        result = OCRResult(
            text="Extracted text",
            confidence=0.88,
            provider="paddle_openai",
            processing_time=5.2,
            page_type="prescription",
        )
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["text"] == "Extracted text"
        assert d["confidence"] == 0.88
        assert d["provider"] == "paddle_openai"
        assert d["processing_time"] == 5.2
        assert d["page_type"] == "prescription"

    def test_default_values(self):
        """Should use default values for optional parameters."""
        result = OCRResult(
            text="Text",
            confidence=0.7,
            provider="test",
            processing_time=1.0,
        )
        assert result.bounding_boxes == []
        assert result.metadata == {}
        assert result.page_type is None


# ─── Tests: Exception Classes ──────────────────────────────────────────────

class TestExceptionClasses:
    """Tests for OCR exception classes."""

    def test_ocr_error(self):
        """Should create OCRError."""
        err = OCRError("Test error")
        assert str(err) == "Test error"

    def test_ocr_config_error(self):
        """Should create OCRConfigError."""
        err = OCRConfigError("Not configured")
        assert isinstance(err, OCRError)

    def test_ocr_processing_error(self):
        """Should create OCRProcessingError."""
        err = OCRProcessingError("Processing failed")
        assert isinstance(err, OCRError)


# ─── Tests: PaddleOCR Provider ─────────────────────────────────────────────

class TestPaddleOCRProvider:
    """Tests for PaddleOCR-based text detection."""

    def test_paddleocr_with_text(self, sample_image):
        """Should extract text using PaddleOCR."""
        from app.ai.ocr_engine import _ocr_with_paddleocr

        try:
            result = _ocr_with_paddleocr(sample_image)
            assert isinstance(result, OCRResult)
            assert result.provider == "paddle"
            assert result.processing_time > 0
            assert result.confidence >= 0
        except OCRConfigError:
            pytest.skip("PaddleOCR not configured")
        except Exception as e:
            pytest.fail(f"PaddleOCR failed: {e}")


# ─── Tests: Tesseract Provider ─────────────────────────────────────────────

class TestTesseractProvider:
    """Tests for Tesseract fallback OCR."""

    def test_tesseract_with_text(self, sample_image):
        """Should extract text using Tesseract."""
        from app.ai.ocr_engine import _ocr_with_tesseract

        try:
            result = _ocr_with_tesseract(sample_image)
            assert isinstance(result, OCRResult)
            assert result.provider == "tesseract"
            assert result.processing_time > 0
        except OCRConfigError:
            pytest.skip("Tesseract not configured")
        except Exception as e:
            pytest.fail(f"Tesseract failed: {e}")


# ─── Tests: OpenAI Provider ────────────────────────────────────────────────

class TestOpenAIProvider:
    """Tests for OpenAI handwriting interpretation."""

    def test_openai_requires_api_key(self, sample_image):
        """Should raise OCRConfigError if OpenAI API key not configured."""
        from app.ai.ocr_engine import _ocr_with_openai
        from app.core.config import settings

        if settings.openai_api_key:
            pytest.skip("OpenAI API key configured - manual testing required")

        with pytest.raises(OCRConfigError):
            _ocr_with_openai("detected text", sample_image)


# ─── Tests: AWS Textract Provider ──────────────────────────────────────────

class TestTextractProvider:
    """Tests for AWS Textract structured extraction."""

    def test_textract_requires_aws_config(self, sample_image):
        """Should fail gracefully if AWS not configured."""
        from app.ai.ocr_engine import _ocr_with_textract
        from app.core.config import settings

        if all(
            [
                getattr(settings, "aws_textract_region", None),
                getattr(settings, "aws_textract_access_key_id", None),
                getattr(settings, "aws_textract_secret_access_key", None),
            ]
        ):
            pytest.skip("AWS Textract configured - manual testing required")

        with pytest.raises(OCRConfigError):
            _ocr_with_textract(sample_image)


# ─── Tests: Main OCR Router ────────────────────────────────────────────────

class TestRunHybridOcr:
    """Tests for run_hybrid_ocr main function."""

    def test_run_hybrid_ocr_prescription(self, prescription_img):
        """Should route prescription to paddle_openai strategy."""
        from app.ai.ocr_engine import run_hybrid_ocr

        try:
            result = run_hybrid_ocr(prescription_img, page_type=PageType.PRESCRIPTION)
            assert isinstance(result, OCRResult)
            assert result.page_type == "prescription"
        except (OCRConfigError, OCRProcessingError) as e:
            pytest.skip(f"OCR not fully configured: {e}")
        except Exception as e:
            pytest.fail(f"run_hybrid_ocr failed unexpectedly: {e}")

    def test_run_hybrid_ocr_blank(self):
        """Should skip blank pages."""
        from app.ai.ocr_engine import run_hybrid_ocr

        blank = Image.new("RGB", (800, 1100), "white")
        result = run_hybrid_ocr(blank, page_type=PageType.BLANK)
        assert result.text == ""
        assert result.provider == "skip"

    def test_run_hybrid_ocr_identity(self):
        """Should skip identity documents for security."""
        from app.ai.ocr_engine import run_hybrid_ocr

        identity = Image.new("RGB", (800, 1100), "white")
        result = run_hybrid_ocr(identity, page_type=PageType.IDENTITY)
        assert result.text == ""
        assert result.provider == "skip"


# ─── Tests: Routing Logic ──────────────────────────────────────────────────

class TestRoutingLogic:
    """Tests for OCR routing logic."""

    def test_strategy_mapping(self):
        """All page types should have defined strategies."""
        from app.ai.page_classifier import get_ocr_strategy

        strategies = {
            PageType.PRESCRIPTION: "paddle_openai",
            PageType.LAB_REPORT: "textract",
            PageType.INVOICE_BILL: "textract",
            PageType.IDENTITY: "skip",
            PageType.OTHER_MEDICAL: "paddle_only",
            PageType.BLANK: "skip",
            PageType.UNKNOWN: "paddle_only",
        }

        for page_type, expected_strategy in strategies.items():
            actual = get_ocr_strategy(page_type)
            assert actual == expected_strategy, f"Wrong strategy for {page_type}"


# ─── Tests: Performance ────────────────────────────────────────────────────

class TestPerformance:
    """Performance tests for OCR engine."""

    def test_processing_time_tracked(self, sample_image):
        """Should track processing time."""
        from app.ai.ocr_engine import _ocr_with_paddleocr

        try:
            result = _ocr_with_paddleocr(sample_image)
            assert result.processing_time > 0
        except OCRConfigError:
            pytest.skip("PaddleOCR not configured")
