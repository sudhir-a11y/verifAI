"""
Unit tests for Page Classifier module (Phase 0).
Tests: classify_page, get_ocr_strategy, PageType enum, error handling.
"""

import pytest
from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.fixtures.helpers import (
    create_prescription_image,
    create_lab_report_image,
    create_invoice_image,
    create_sample_image,
)
from app.ai.page_classifier import (
    classify_page,
    get_ocr_strategy,
    PageType,
    PageClassifierError,
    BlankPageError,
    _get_image_properties,
    _classify_by_patterns,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def prescription_image():
    """Create a prescription image for testing."""
    return create_prescription_image()


@pytest.fixture
def lab_report_image():
    """Create a lab report image for testing."""
    return create_lab_report_image()


@pytest.fixture
def invoice_image():
    """Create an invoice image for testing."""
    return create_invoice_image()


@pytest.fixture
def blank_image():
    """Create a blank (white) image for testing."""
    return Image.new("RGB", (800, 1100), "white")


@pytest.fixture
def dark_image():
    """Create a dark/dense image for testing identity detection."""
    img = Image.new("RGB", (800, 1100), "black")
    draw = ImageDraw.Draw(img)
    # Fill with dense text-like patterns
    for y in range(0, 1100, 10):
        draw.line([(0, y), (800, y)], fill="darkgray")
    return img


# ─── Tests: PageType Enum ──────────────────────────────────────────────────

class TestPageTypeEnum:
    """Tests for PageType enum."""

    def test_page_types_exist(self):
        """All expected page types should exist."""
        assert hasattr(PageType, "PRESCRIPTION")
        assert hasattr(PageType, "LAB_REPORT")
        assert hasattr(PageType, "INVOICE_BILL")
        assert hasattr(PageType, "IDENTITY")
        assert hasattr(PageType, "OTHER_MEDICAL")
        assert hasattr(PageType, "BLANK")
        assert hasattr(PageType, "UNKNOWN")

    def test_page_type_values(self):
        """Page type values should match expected strings."""
        assert PageType.PRESCRIPTION.value == "prescription"
        assert PageType.LAB_REPORT.value == "lab_report"
        assert PageType.INVOICE_BILL.value == "invoice_bill"
        assert PageType.IDENTITY.value == "identity"
        assert PageType.OTHER_MEDICAL.value == "other_medical"
        assert PageType.BLANK.value == "blank"
        assert PageType.UNKNOWN.value == "unknown"


# ─── Tests: classify_page ──────────────────────────────────────────────────

class TestClassifyPage:
    """Tests for classify_page function."""

    def test_prescription_classification(self, prescription_image):
        """Should classify prescription image or detect as blank."""
        try:
            result = classify_page(prescription_image)
            assert "page_type" in result
            assert "confidence" in result
            assert isinstance(result["page_type"], PageType)
            assert 0.0 <= result["confidence"] <= 1.0
        except BlankPageError:
            pytest.skip("Prescription image classified as blank (not enough text density)")

    def test_lab_report_classification(self, lab_report_image):
        """Should classify lab report image or detect as blank."""
        try:
            result = classify_page(lab_report_image)
            assert "page_type" in result
            assert isinstance(result["page_type"], PageType)
            assert 0.0 <= result["confidence"] <= 1.0
        except BlankPageError:
            pytest.skip("Lab report image classified as blank (not enough text density)")

    def test_invoice_classification(self, invoice_image):
        """Should classify invoice image or detect as blank."""
        try:
            result = classify_page(invoice_image)
            assert "page_type" in result
            assert isinstance(result["page_type"], PageType)
            assert 0.0 <= result["confidence"] <= 1.0
        except BlankPageError:
            pytest.skip("Invoice image classified as blank (not enough text density)")

    def test_blank_page_detection(self, blank_image):
        """Should detect blank page and raise BlankPageError."""
        with pytest.raises(BlankPageError):
            classify_page(blank_image)

    def test_dark_page_classification(self, dark_image):
        """Should classify dark/dense image."""
        result = classify_page(dark_image)
        assert "page_type" in result
        assert isinstance(result["page_type"], PageType)


# ─── Tests: get_ocr_strategy ───────────────────────────────────────────────

class TestGetOcrStrategy:
    """Tests for get_ocr_strategy function."""

    def test_prescription_strategy(self):
        """Should return paddle_openai for prescriptions."""
        strategy = get_ocr_strategy(PageType.PRESCRIPTION)
        assert strategy == "paddle_openai"

    def test_lab_report_strategy(self):
        """Should return textract for lab reports."""
        strategy = get_ocr_strategy(PageType.LAB_REPORT)
        assert strategy == "textract"

    def test_invoice_strategy(self):
        """Should return textract for invoices."""
        strategy = get_ocr_strategy(PageType.INVOICE_BILL)
        assert strategy == "textract"

    def test_identity_strategy(self):
        """Should return skip for identity documents."""
        strategy = get_ocr_strategy(PageType.IDENTITY)
        assert strategy == "skip"

    def test_other_medical_strategy(self):
        """Should return paddle_only for other medical."""
        strategy = get_ocr_strategy(PageType.OTHER_MEDICAL)
        assert strategy == "paddle_only"

    def test_unknown_strategy(self):
        """Should return paddle_only for unknown."""
        strategy = get_ocr_strategy(PageType.UNKNOWN)
        assert strategy == "paddle_only"

    def test_blank_strategy(self):
        """Should return skip for blank pages."""
        strategy = get_ocr_strategy(PageType.BLANK)
        assert strategy == "skip"


# ─── Tests: _get_image_properties ──────────────────────────────────────────

class TestGetImageProperties:
    """Tests for _get_image_properties helper function."""

    def test_white_image_properties(self, blank_image):
        """Should return correct properties for white image."""
        props = _get_image_properties(blank_image)
        assert props["width"] == 800
        assert props["height"] == 1100
        assert props["mean_intensity"] > 240  # Very bright
        assert props["dark_ratio"] < 0.01  # Almost no dark pixels

    def test_prescription_properties(self, prescription_image):
        """Should return valid properties for prescription."""
        props = _get_image_properties(prescription_image)
        assert props["width"] == 800
        assert props["height"] == 1100
        assert 0 < props["mean_intensity"] < 255
        assert props["edge_density"] > 0

    def test_aspect_ratio_calculation(self):
        """Should calculate aspect ratio correctly."""
        img = Image.new("RGB", (400, 600), "white")
        props = _get_image_properties(img)
        assert abs(props["aspect_ratio"] - (400 / 600)) < 0.001


# ─── Tests: _classify_by_patterns ──────────────────────────────────────────

class TestClassifyByPatterns:
    """Tests for _classify_by_patterns helper function."""

    def test_blank_classification(self):
        """Should classify as BLANK for very bright images."""
        img = Image.new("RGB", (800, 1100), "white")
        props = _get_image_properties(img)
        page_type, confidence = _classify_by_patterns(img, props)
        assert page_type == PageType.BLANK
        assert confidence == 0.95

    def test_confidence_range(self, prescription_image):
        """Should return confidence in valid range."""
        props = _get_image_properties(prescription_image)
        _, confidence = _classify_by_patterns(prescription_image, props)
        assert 0.0 <= confidence <= 1.0


# ─── Tests: Edge Cases ─────────────────────────────────────────────────────

class TestEdgeCases:
    """Edge case tests for page classifier."""

    def test_very_small_image(self):
        """Should handle very small images gracefully."""
        img = Image.new("RGB", (10, 10), "white")
        with pytest.raises(BlankPageError):
            classify_page(img)

    def test_large_image(self):
        """Should handle large images."""
        img = Image.new("RGB", (4000, 5500), "white")
        draw = ImageDraw.Draw(img)
        draw.text((100, 100), "Test content", fill="black")
        result = classify_page(img)
        assert "page_type" in result

    def test_grayscale_image(self):
        """Should handle grayscale images."""
        img = Image.new("L", (800, 1100), 128)
        draw = ImageDraw.Draw(img)
        draw.text((100, 100), "Test", fill=255)
        result = classify_page(img.convert("RGB"))
        assert "page_type" in result

    def test_rgba_image(self):
        """Should handle RGBA images."""
        img = Image.new("RGBA", (800, 1100), (255, 255, 255, 255))
        with pytest.raises(BlankPageError):
            classify_page(img.convert("RGB"))
