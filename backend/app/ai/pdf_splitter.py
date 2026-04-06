"""
Phase 0: PDF Splitter Module
Splits multi-page PDFs into individual page images for OCR processing.
Uses pypdfium2 for PDF rendering (no external Poppler dependency).
"""

import logging
from typing import List

from PIL import Image

logger = logging.getLogger(__name__)


class PDFSplitterError(Exception):
    """Base exception for PDF splitting errors."""

    pass


class InvalidPDFError(PDFSplitterError):
    """Raised when PDF is invalid or corrupted."""

    pass


class EmptyPDFError(PDFSplitterError):
    """Raised when PDF has no pages."""

    pass


def split_pdf(
    pdf_path: str,
    page_range: tuple[int, int] | None = None,
    dpi: int = 300,
) -> List[Image.Image]:
    """
    Split PDF into individual page images.

    Args:
        pdf_path: Path to PDF file
        page_range: Optional tuple (start_page, end_page) - 0-indexed, end_page exclusive.
                   If None, processes all pages.
        dpi: DPI for PDF rendering (affects image quality)

    Returns:
        List of PIL Image objects (one per page)

    Raises:
        InvalidPDFError: If PDF is invalid or corrupted
        EmptyPDFError: If PDF has no pages

    Example:
        images = split_pdf("prescription.pdf")
        images = split_pdf("report.pdf", page_range=(0, 5))  # First 5 pages
    """
    try:
        try:
            import pypdfium2 as pdfium
        except ImportError as e:
            raise PDFSplitterError(
                "pypdfium2 not installed. Install with: pip install pypdfium2"
            ) from e

        try:
            pdf = pdfium.PdfDocument(pdf_path)
        except Exception as e:
            raise InvalidPDFError(f"Cannot open PDF: {pdf_path}") from e

        total_pages = len(pdf)
        if total_pages == 0:
            raise EmptyPDFError(f"PDF has no pages: {pdf_path}")

        logger.info(f"PDF '{pdf_path}' has {total_pages} pages")

        # Determine page range
        start_page = 0
        end_page = total_pages

        if page_range:
            start_page, end_page = page_range
            if start_page < 0:
                raise PDFSplitterError(f"Invalid start page: {start_page}")
            if end_page > total_pages:
                end_page = total_pages
            if start_page >= end_page:
                return []  # Empty range
            logger.info(f"Processing pages {start_page}-{end_page - 1}")

        scale = max(float(dpi) / 72.0, 0.1)
        images: list[Image.Image] = []
        for page_index in range(start_page, end_page):
            page = pdf.get_page(page_index)
            try:
                pil_image = page.render(scale=scale).to_pil()
            finally:
                page.close()
            images.append(pil_image)

        logger.info(f"Successfully split PDF into {len(images)} images")
        return images

    except PDFSplitterError:
        raise
    except FileNotFoundError as e:
        logger.error(f"PDF file not found: {pdf_path}")
        raise InvalidPDFError(f"PDF file not found: {pdf_path}") from e
    except Exception as e:
        logger.error(f"Error splitting PDF: {str(e)}")
        raise InvalidPDFError(f"Cannot split PDF: {str(e)}") from e


def get_pdf_page_count(pdf_path: str) -> int:
    """
    Get total number of pages in PDF without splitting.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Number of pages in PDF

    Raises:
        InvalidPDFError: If PDF is invalid or file not found
    """
    try:
        from pypdf import PdfReader

        with open(pdf_path, "rb") as f:
            pdf_reader = PdfReader(f)
            count = len(pdf_reader.pages)
        return count
    except FileNotFoundError as e:
        raise InvalidPDFError(f"PDF file not found: {pdf_path}") from e
    except Exception as e:
        raise InvalidPDFError(f"Cannot read PDF: {str(e)}") from e
