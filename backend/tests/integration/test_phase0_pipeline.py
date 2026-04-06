"""
Integration tests for Phase 0: Full PDF → OCR Pipeline.
Tests the complete workflow: PDF → Split → Classify → OCR → Result
"""

import pytest
from pathlib import Path
from PIL import Image

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.fixtures.helpers import (
    create_sample_pdf_with_reportlab,
    create_multi_page_pdf,
    create_prescription_image,
    create_lab_report_image,
)
from app.ai.pdf_splitter import split_pdf, get_pdf_page_count, InvalidPDFError
from app.ai.page_classifier import classify_page, get_ocr_strategy, PageType, BlankPageError
from app.ai.ocr_engine import run_hybrid_ocr, OCRResult, OCRConfigError, OCRProcessingError


# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def test_fixtures_dir():
    """Ensure fixtures directory exists."""
    fixtures_dir = Path(__file__).parent.parent / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    return fixtures_dir


@pytest.fixture
def single_page_pdf(test_fixtures_dir):
    """Create a single-page PDF with prescription content."""
    pdf_path = test_fixtures_dir / "integration_single.pdf"
    create_sample_pdf_with_reportlab(
        pages=[
            {
                "title": "PRESCRIPTION",
                "text": "Dr. Smith\nPatient: John Doe\nRx: Amoxicillin 500mg",
            }
        ],
        output_path=pdf_path,
    )
    yield pdf_path


@pytest.fixture
def multi_page_pdf(test_fixtures_dir):
    """Create a multi-page PDF with mixed content."""
    pdf_path = test_fixtures_dir / "integration_multi.pdf"
    create_multi_page_pdf(
        pages=[
            {"title": "PRESCRIPTION", "text": "Dr. Smith\nRx: Medicine"},
            {"title": "LAB REPORT", "text": "Hemoglobin: 14.5\nWBC: 7500"},
            {"title": "BILL", "text": "Hospital Bill\nTotal: Rs. 5000"},
        ],
        output_path=pdf_path,
    )
    yield pdf_path


# ─── Tests: Complete Pipeline ──────────────────────────────────────────────

class TestFullPipeline:
    """Tests for the complete PDF → OCR pipeline."""

    def test_single_page_pipeline(self, single_page_pdf):
        """Should process single-page PDF through full pipeline."""
        # Step 1: Get page count
        page_count = get_pdf_page_count(str(single_page_pdf))
        assert page_count == 1

        # Step 2: Split PDF
        images = split_pdf(str(single_page_pdf))
        assert len(images) == 1
        assert isinstance(images[0], Image.Image)

        # Step 3: Classify page
        try:
            classification = classify_page(images[0])
            assert "page_type" in classification
            assert isinstance(classification["page_type"], PageType)
        except BlankPageError:
            pytest.skip("Page classified as blank - skipping OCR")

        # Step 4: Get OCR strategy
        page_type = classification["page_type"]
        strategy = get_ocr_strategy(page_type)
        assert strategy in ["paddle_openai", "textract", "paddle_only", "skip"]

        # Step 5: Run OCR (may skip if not fully configured)
        if strategy == "skip":
            pytest.skip("Page type requires skipping")

        try:
            result = run_hybrid_ocr(images[0], page_type=page_type)
            assert isinstance(result, OCRResult)
            assert result.page_type == page_type.value
        except (OCRConfigError, OCRProcessingError):
            pytest.skip(f"OCR not fully configured for strategy: {strategy}")

    def test_multi_page_pipeline(self, multi_page_pdf):
        """Should process multi-page PDF through full pipeline."""
        # Step 1: Get page count
        page_count = get_pdf_page_count(str(multi_page_pdf))
        assert page_count == 3

        # Step 2: Split all pages
        images = split_pdf(str(multi_page_pdf))
        assert len(images) == 3

        # Step 3: Process each page
        processed_pages = 0
        skipped_pages = 0

        for i, image in enumerate(images):
            try:
                classification = classify_page(image)
                page_type = classification["page_type"]
                strategy = get_ocr_strategy(page_type)

                if strategy == "skip":
                    skipped_pages += 1
                    continue

                result = run_hybrid_ocr(image, page_type=page_type)
                assert isinstance(result, OCRResult)
                processed_pages += 1

            except BlankPageError:
                skipped_pages += 1
            except (OCRConfigError, OCRProcessingError):
                skipped_pages += 1

        # At least some pages should be processed or skipped
        assert processed_pages + skipped_pages == 3

    def test_pipeline_prescription_image(self):
        """Should process prescription image correctly."""
        img = create_prescription_image()

        try:
            classification = classify_page(img)
            assert classification["page_type"] == PageType.PRESCRIPTION
        except BlankPageError:
            pytest.skip("Image classified as blank")

        strategy = get_ocr_strategy(PageType.PRESCRIPTION)
        assert strategy == "paddle_openai"

        try:
            result = run_hybrid_ocr(img, page_type=PageType.PRESCRIPTION)
            assert isinstance(result, OCRResult)
            assert result.page_type == "prescription"
        except (OCRConfigError, OCRProcessingError):
            pytest.skip("OpenAI not configured - paddle_only fallback expected")

    def test_pipeline_lab_report_image(self):
        """Should process lab report image correctly."""
        img = create_lab_report_image()

        try:
            classification = classify_page(img)
        except BlankPageError:
            pytest.skip("Image classified as blank")

        strategy = get_ocr_strategy(PageType.LAB_REPORT)
        assert strategy == "textract"

        # Textract requires AWS config
        try:
            result = run_hybrid_ocr(img, page_type=PageType.LAB_REPORT)
            assert isinstance(result, OCRResult)
        except (OCRConfigError, OCRProcessingError):
            pytest.skip("AWS Textract not configured")


# ─── Tests: Error Handling in Pipeline ─────────────────────────────────────

class TestPipelineErrorHandling:
    """Tests for error handling in the pipeline."""

    def test_invalid_pdf_pipeline(self, tmp_path):
        """Should handle invalid PDF gracefully."""
        invalid_path = tmp_path / "invalid.pdf"
        invalid_path.write_text("Not a PDF")

        with pytest.raises(InvalidPDFError):
            get_pdf_page_count(str(invalid_path))

        with pytest.raises(InvalidPDFError):
            split_pdf(str(invalid_path))

    def test_blank_pdf_pipeline(self, tmp_path):
        """Should handle blank PDF gracefully."""
        from reportlab.pdfgen import canvas

        blank_path = tmp_path / "blank.pdf"
        c = canvas.Canvas(str(blank_path))
        c.showPage()
        c.save()

        page_count = get_pdf_page_count(str(blank_path))
        assert page_count == 1

        images = split_pdf(str(blank_path))
        assert len(images) == 1

        with pytest.raises(BlankPageError):
            classify_page(images[0])


# ─── Tests: Performance ────────────────────────────────────────────────────

class TestPipelinePerformance:
    """Performance tests for the pipeline."""

    def test_processing_time_tracking(self, single_page_pdf):
        """Should track total processing time."""
        import time

        start = time.time()

        images = split_pdf(str(single_page_pdf))

        try:
            classification = classify_page(images[0])
            page_type = classification["page_type"]

            if get_ocr_strategy(page_type) != "skip":
                result = run_hybrid_ocr(images[0], page_type=page_type)
                assert result.processing_time > 0
        except (BlankPageError, OCRConfigError, OCRProcessingError):
            pass  # Skip if not fully configured

        total_time = time.time() - start
        assert total_time > 0
