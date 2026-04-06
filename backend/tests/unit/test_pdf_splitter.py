"""
Unit tests for PDF Splitter module (Phase 0).
Tests: split_pdf, get_pdf_page_count, error handling.
"""

import pytest
from pathlib import Path
from PIL import Image

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.fixtures.helpers import (
    create_sample_pdf_with_reportlab,
    create_blank_pdf_with_reportlab,
    create_multi_page_pdf,
)
from app.ai.pdf_splitter import (
    split_pdf,
    get_pdf_page_count,
    PDFSplitterError,
    InvalidPDFError,
    EmptyPDFError,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def test_fixtures_dir():
    """Ensure fixtures directory exists and return path."""
    fixtures_dir = Path(__file__).parent.parent / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    return fixtures_dir


@pytest.fixture
def single_page_pdf(test_fixtures_dir):
    """Create a single-page PDF for testing."""
    pdf_path = test_fixtures_dir / "single_page.pdf"
    create_sample_pdf_with_reportlab(
        pages=[{"title": "Test Document", "text": "Line 1\nLine 2\nLine 3"}],
        output_path=pdf_path,
    )
    yield pdf_path
    # pdf_path.unlink(missing_ok=True)


@pytest.fixture
def multi_page_pdf(test_fixtures_dir):
    """Create a multi-page PDF for testing."""
    pdf_path = test_fixtures_dir / "multi_page.pdf"
    create_multi_page_pdf(
        pages=[
            {"title": "Page 1", "text": "Content 1"},
            {"title": "Page 2", "text": "Content 2"},
            {"title": "Page 3", "text": "Content 3"},
        ],
        output_path=pdf_path,
    )
    yield pdf_path
    # pdf_path.unlink(missing_ok=True)


@pytest.fixture
def blank_pdf(test_fixtures_dir):
    """Create a blank PDF for testing."""
    pdf_path = test_fixtures_dir / "blank.pdf"
    create_blank_pdf_with_reportlab(output_path=pdf_path)
    yield pdf_path
    # pdf_path.unlink(missing_ok=True)


@pytest.fixture
def invalid_pdf_path(test_fixtures_dir):
    """Return path to a non-PDF file."""
    txt_path = test_fixtures_dir / "not_a_pdf.pdf"
    txt_path.write_text("This is not a PDF file")
    yield txt_path
    # txt_path.unlink(missing_ok=True)


# ─── Tests: get_pdf_page_count ──────────────────────────────────────────────

class TestGetPdfPageCount:
    """Tests for get_pdf_page_count function."""

    def test_single_page_pdf(self, single_page_pdf):
        """Should return 1 for a single-page PDF."""
        count = get_pdf_page_count(str(single_page_pdf))
        assert count == 1

    def test_multi_page_pdf(self, multi_page_pdf):
        """Should return correct page count for multi-page PDF."""
        count = get_pdf_page_count(str(multi_page_pdf))
        assert count == 3

    def test_blank_pdf(self, blank_pdf):
        """Should return 1 for a blank PDF."""
        count = get_pdf_page_count(str(blank_pdf))
        assert count == 1

    def test_invalid_pdf(self, invalid_pdf_path):
        """Should raise InvalidPDFError for invalid file."""
        with pytest.raises(InvalidPDFError):
            get_pdf_page_count(str(invalid_pdf_path))

    def test_nonexistent_file(self):
        """Should raise InvalidPDFError for nonexistent file."""
        with pytest.raises(InvalidPDFError):
            get_pdf_page_count("/nonexistent/path/file.pdf")


# ─── Tests: split_pdf ───────────────────────────────────────────────────────

class TestSplitPdf:
    """Tests for split_pdf function."""

    def test_split_single_page(self, single_page_pdf):
        """Should split single-page PDF into one image."""
        images = split_pdf(str(single_page_pdf))
        assert len(images) == 1
        assert all(isinstance(img, Image.Image) for img in images)

    def test_split_all_pages(self, multi_page_pdf):
        """Should split multi-page PDF into correct number of images."""
        images = split_pdf(str(multi_page_pdf))
        assert len(images) == 3
        assert all(isinstance(img, Image.Image) for img in images)

    def test_split_page_range(self, multi_page_pdf):
        """Should split only specified page range."""
        images = split_pdf(str(multi_page_pdf), page_range=(0, 2))
        assert len(images) == 2

    def test_split_page_range_partial(self, multi_page_pdf):
        """Should split from start_page to end of PDF if end_page is None or large."""
        images = split_pdf(str(multi_page_pdf), page_range=(1, 10))
        assert len(images) == 2  # Pages 1 and 2 (0-indexed)

    def test_split_blank_pdf(self, blank_pdf):
        """Should split blank PDF into one image."""
        images = split_pdf(str(blank_pdf))
        assert len(images) == 1
        assert isinstance(images[0], Image.Image)

    def test_invalid_pdf(self, invalid_pdf_path):
        """Should raise InvalidPDFError for invalid file."""
        with pytest.raises(InvalidPDFError):
            split_pdf(str(invalid_pdf_path))

    def test_nonexistent_file(self):
        """Should raise InvalidPDFError for nonexistent file."""
        with pytest.raises(InvalidPDFError):
            split_pdf("/nonexistent/path/file.pdf")

    def test_image_properties(self, single_page_pdf):
        """Should return images with valid properties."""
        images = split_pdf(str(single_page_pdf))
        img = images[0]
        assert img.width > 0
        assert img.height > 0
        assert img.mode in ("RGB", "RGBA", "L")

    def test_dpi_parameter(self, single_page_pdf):
        """Should respect DPI parameter."""
        images_150 = split_pdf(str(single_page_pdf), dpi=150)
        images_300 = split_pdf(str(single_page_pdf), dpi=300)

        # Higher DPI should produce larger images
        assert images_300[0].width >= images_150[0].width


# ─── Tests: Edge Cases ──────────────────────────────────────────────────────

class TestSplitPdfEdgeCases:
    """Edge case tests for PDF splitter."""

    def test_empty_page_range(self, multi_page_pdf):
        """Should handle empty page range gracefully."""
        images = split_pdf(str(multi_page_pdf), page_range=(0, 0))
        assert len(images) == 0

    def test_negative_page_range(self, multi_page_pdf):
        """Should handle negative page range gracefully."""
        with pytest.raises((PDFSplitterError, ValueError, IndexError)):
            split_pdf(str(multi_page_pdf), page_range=(-1, 2))

    def test_large_dpi(self, single_page_pdf):
        """Should handle very high DPI values."""
        images = split_pdf(str(single_page_pdf), dpi=600)
        assert len(images) == 1
        assert images[0].width > 0
