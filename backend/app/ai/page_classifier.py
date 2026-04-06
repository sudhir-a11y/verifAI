"""
Phase 0: Page Classifier Module
Classifies document pages into types (prescription, lab_report, invoice, identity, other, blank).
Uses rule-based detection with image properties analysis.
"""

import logging
from enum import Enum
from typing import Tuple

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class PageType(str, Enum):
    """Document page type classification."""

    PRESCRIPTION = "prescription"
    LAB_REPORT = "lab_report"
    INVOICE_BILL = "invoice_bill"
    IDENTITY = "identity"
    OTHER_MEDICAL = "other_medical"
    BLANK = "blank"
    UNKNOWN = "unknown"


class PageClassifierError(Exception):
    """Base exception for page classification errors."""

    pass


class BlankPageError(PageClassifierError):
    """Raised when page is blank or empty."""

    pass


def _get_image_properties(image: Image.Image) -> dict:
    """
    Extract image properties for classification.

    Args:
        image: PIL Image object

    Returns:
        Dictionary with image properties
    """
    # Convert to numpy array for analysis
    img_array = np.array(image.convert("L"))  # Grayscale

    # Calculate properties
    height, width = img_array.shape
    total_pixels = height * width

    # Darkness/brightness
    mean_intensity = np.mean(img_array)
    dark_pixels = np.sum(img_array < 100)
    dark_ratio = dark_pixels / total_pixels

    # Edge density (text indicator)
    # Simple edge detection: high difference between adjacent pixels
    diff_h = np.abs(np.diff(img_array, axis=0)).mean()
    diff_v = np.abs(np.diff(img_array, axis=1)).mean()
    edge_density = (diff_h + diff_v) / 2

    # Text area detection (vertical/horizontal text patterns)
    # Count frequent intensity levels (indicates text)
    # Use a fixed range to avoid degenerate histograms on constant-intensity images.
    hist, _ = np.histogram(img_array, bins=256, range=(0, 255))
    text_indicators = np.sum(hist[50:200])  # Mid-range intensity for text

    return {
        "width": width,
        "height": height,
        "aspect_ratio": width / height if height > 0 else 0,
        "mean_intensity": mean_intensity,
        "dark_ratio": dark_ratio,
        "edge_density": edge_density,
        "text_indicators": text_indicators,
    }


def _classify_by_patterns(
    image: Image.Image, properties: dict
) -> Tuple[PageType, float]:
    """
    Classify page based on visual patterns.

    Classification logic:
    - BLANK: mean_intensity > 240 or text_indicators < 1000
    - IDENTITY: usually dense text + faces (high edge density)
    - INVOICE: columnar layout + numbers (specific patterns)
    - PRESCRIPTION: handwriting patterns + medical symbols + patient name
    - LAB_REPORT: structured tabular data + values/units
    - OTHER_MEDICAL: medical content but unclear type

    Args:
        image: PIL Image object
        properties: Dictionary from _get_image_properties

    Returns:
        Tuple of (PageType, confidence_score)
    """
    confidence = 0.5  # Base confidence
    detected_type = PageType.UNKNOWN

    # Rule 1: Blank page detection
    # Be conservative: only treat near-pure-white pages as blank.
    if (
        properties["mean_intensity"] > 250
        and properties["dark_ratio"] < 0.000005
        and properties["edge_density"] < 0.5
        and properties["text_indicators"] < 500
    ):
        logger.debug("Detected as BLANK: near-empty page")
        return PageType.BLANK, 0.95

    # Rule 2: Identity document (dense text + faces)
    if properties["edge_density"] > 15 and properties["dark_ratio"] > 0.35:
        logger.debug("Detected as IDENTITY: high edge density + dark areas")
        return PageType.IDENTITY, 0.85

    # Rule 3: Lab report (dense structured text)
    # Synthetic lab reports tend to have higher text density.
    if properties["edge_density"] > 2.6 and properties["text_indicators"] > 7000:
        logger.debug("Detected as LAB_REPORT: dense structured content")
        detected_type = PageType.LAB_REPORT
        confidence = 0.70

    # Rule 4: Prescription (moderate density, header + short lines)
    elif properties["edge_density"] > 1.8 and properties["text_indicators"] > 5400:
        logger.debug("Detected as PRESCRIPTION: moderate text density")
        detected_type = PageType.PRESCRIPTION
        confidence = 0.65

    # Rule 5: Invoice/Bill (moderate density, often slightly lower than prescriptions)
    elif properties["edge_density"] > 1.6 and properties["text_indicators"] > 4500:
        logger.debug("Detected as INVOICE_BILL: moderate structured content")
        detected_type = PageType.INVOICE_BILL
        confidence = 0.60

    # Rule 6: Other medical (some medical content detected)
    if detected_type == PageType.UNKNOWN and properties["text_indicators"] > 1500:
        logger.debug("Detected as OTHER_MEDICAL: general medical content")
        detected_type = PageType.OTHER_MEDICAL
        confidence = 0.50

    return detected_type, confidence


def _read_text_hints(image: Image.Image) -> dict:
    """
    Extract text hints from image for keyword-based refinement.
    This is a placeholder for OCR-based hints in future versions.

    Args:
        image: PIL Image object

    Returns:
        Dictionary with text-based hints
    """
    # In Phase 1, we would use PaddleOCR here to get actual keywords
    # For now, return empty hints
    return {
        "has_patient_name": False,
        "has_prescription_keywords": False,
        "has_lab_keywords": False,
        "has_invoice_keywords": False,
        "has_identity_keywords": False,
    }


def classify_page(image: Image.Image) -> dict:
    """
    Classify a document page into types.

    Args:
        image: PIL Image object

    Returns:
        Dictionary with classification results:
        {
            'page_type': PageType,
            'confidence': float (0-1),
            'properties': dict,
            'notes': str
        }

    Raises:
        PageClassifierError: If classification fails
        BlankPageError: If page is blank

    Example:
        result = classify_page(image)
        if result['page_type'] == PageType.PRESCRIPTION:
            # Use OpenAI GPT-4o for handwriting
            text = process_with_openai(image)
        elif result['page_type'] == PageType.LAB_REPORT:
            # Use Textract for structured data
            text = process_with_textract(image)
    """
    try:
        # Step 1: Extract properties
        properties = _get_image_properties(image)
        logger.debug(f"Image properties: {properties}")

        # Step 2: Pattern-based classification
        page_type, pattern_confidence = _classify_by_patterns(image, properties)

        # Step 3: Text hints (for future refinement with actual OCR)
        text_hints = _read_text_hints(image)
        logger.debug(f"Text hints: {text_hints}")

        # Blank page check
        if page_type == PageType.BLANK:
            raise BlankPageError(f"Page is blank or has minimal content")

        logger.info(
            f"Page classified as {page_type.value} "
            f"(confidence: {pattern_confidence:.2f})"
        )

        return {
            "page_type": page_type,
            "confidence": pattern_confidence,
            "properties": properties,
            "text_hints": text_hints,
            "notes": f"Classified as {page_type.value} based on visual patterns",
        }

    except BlankPageError:
        raise
    except Exception as e:
        logger.error(f"Error classifying page: {str(e)}")
        raise PageClassifierError(f"Cannot classify page: {str(e)}") from e


def get_ocr_strategy(page_type: PageType) -> str:
    """
    Determine best OCR strategy for a page type.
    Used by ocr_engine.py to route to appropriate processor.

    Args:
        page_type: PageType classification

    Returns:
        Strategy name: "paddle_openai" | "textract" | "paddle_only" | "skip"
    """
    strategies = {
        PageType.PRESCRIPTION: "paddle_openai",  # Handwriting + OpenAI
        PageType.LAB_REPORT: "textract",  # Structured data
        PageType.INVOICE_BILL: "textract",  # Tables
        PageType.IDENTITY: "skip",  # Security: don't OCR
        PageType.OTHER_MEDICAL: "paddle_only",  # General medical
        PageType.UNKNOWN: "paddle_only",  # Fallback
        PageType.BLANK: "skip",  # Empty page
    }
    return strategies.get(page_type, "paddle_only")
