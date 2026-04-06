"""
Phase 0: Hybrid OCR Engine Module
Implements multi-detector OCR with fallback chain.
Primary: PaddleOCR (detection) → OpenAI (handwriting interpretation) → AWS Textract → Tesseract (fallback)
"""

import logging
import time
from typing import Any, Optional

import numpy as np
from PIL import Image

from app.core.config import settings
from app.ai.page_classifier import PageType, get_ocr_strategy
from app.ai.openai_chat import OpenAIChatError, chat_completions, extract_message_text

logger = logging.getLogger(__name__)


class OCRError(Exception):
    """Base exception for OCR errors."""

    pass


class OCRConfigError(OCRError):
    """Raised when OCR is not configured."""

    pass


class OCRProcessingError(OCRError):
    """Raised when OCR processing fails."""

    pass


class OCRResult:
    """
    Result from OCR processing.

    Attributes:
        text: Extracted text
        confidence: Confidence score (0-1)
        provider: OCR provider used
        bounding_boxes: List of detected text regions (optional)
        processing_time: Time taken in seconds
        page_type: Classified page type
        metadata: Additional provider-specific metadata
    """

    def __init__(
        self,
        text: str,
        confidence: float,
        provider: str,
        processing_time: float,
        page_type: Optional[str] = None,
        bounding_boxes: Optional[list] = None,
        metadata: Optional[dict] = None,
    ):
        self.text = text
        self.confidence = confidence
        self.provider = provider
        self.processing_time = processing_time
        self.page_type = page_type
        self.bounding_boxes = bounding_boxes or []
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        """Convert result to dictionary."""
        return {
            "text": self.text,
            "confidence": self.confidence,
            "provider": self.provider,
            "processing_time": self.processing_time,
            "page_type": self.page_type,
            "bounding_boxes": self.bounding_boxes,
            "metadata": self.metadata,
        }


def _ocr_with_paddleocr(image: Image.Image) -> OCRResult:
    """
    Text detection using PaddleOCR.

    Args:
        image: PIL Image object

    Returns:
        OCRResult with detected text and bounding boxes

    Raises:
        OCRProcessingError: If PaddleOCR fails
    """
    start_time = time.time()

    try:
        try:
            from paddleocr import PaddleOCR
        except ImportError as e:
            raise OCRConfigError(
                "PaddleOCR not installed. Install with: pip install paddleocr"
            ) from e

        if not hasattr(_ocr_with_paddleocr, "_paddleocr_model"):
            logger.info("Initializing PaddleOCR model (first run, may take 30-60s)...")
            try:
                _ocr_with_paddleocr._paddleocr_model = PaddleOCR(
                    use_textline_orientation=True,
                    lang="en",
                )
            except ModuleNotFoundError as e:
                # PaddleOCR can be installed without the heavy paddle runtime.
                if getattr(e, "name", None) == "paddle":
                    raise OCRConfigError(
                        "Paddle runtime (paddlepaddle) not installed; PaddleOCR is not usable."
                    ) from e
                raise

        ocr_model = _ocr_with_paddleocr._paddleocr_model
        img_array = np.array(image)

        logger.debug("Running PaddleOCR detection...")
        results = ocr_model.ocr(img_array, cls=True)

        extracted_text = ""
        bounding_boxes = []
        confidence_scores = []

        if results and results[0]:
            for line in results[0]:
                box, (text, conf) = line
                extracted_text += text + " "
                confidence_scores.append(float(conf))
                bounding_boxes.append(
                    {
                        "box": [[float(p[0]), float(p[1])] for p in box],
                        "text": text,
                        "confidence": float(conf),
                    }
                )

        avg_confidence = (
            sum(confidence_scores) / len(confidence_scores)
            if confidence_scores
            else 0.5
        )

        elapsed = time.time() - start_time
        logger.info(
            f"PaddleOCR: extracted {len(extracted_text)} chars "
            f"(confidence: {avg_confidence:.2f}, time: {elapsed:.2f}s)"
        )

        return OCRResult(
            text=extracted_text.strip(),
            confidence=avg_confidence,
            provider="paddle",
            processing_time=elapsed,
            bounding_boxes=bounding_boxes,
            metadata={"text_regions": len(bounding_boxes)},
        )

    except OCRConfigError:
        raise
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"PaddleOCR failed: {str(e)}")
        raise OCRProcessingError(f"PaddleOCR failed: {str(e)}") from e


def _ocr_with_openai(text: str, image: Image.Image) -> str:
    """
    Interpret handwriting and context using OpenAI vision-capable model.
    Used for prescription handwriting interpretation.

    Args:
        text: Detected text from PaddleOCR
        image: PIL Image object (for context)

    Returns:
        Interpreted text with handwriting corrections

    Raises:
        OCRConfigError: If OpenAI API key not configured
        OCRProcessingError: If API call fails
    """
    if not getattr(settings, "openai_api_key", None):
        raise OCRConfigError("OpenAI API key not configured")

    try:
        import base64
        import io

        img_buffer = io.BytesIO()
        image.save(img_buffer, format="PNG")
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.read()).decode("utf-8")

        prompt = f"""Analyze this medical prescription image.
The following text was already detected by OCR: "{text}"

Your task:
1. Identify handwritten content that may have been misread by OCR
2. Interpret doctor's handwriting and medical abbreviations
3. Correct the text for accuracy
4. Focus on: patient name, diagnosis, medications, dosage, frequency, duration
5. Flag any unclear or ambiguous handwriting

Return ONLY the corrected and interpreted text, no explanations."""

        model_name = getattr(settings, "openai_vision_model", "gpt-5.1")
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_base64}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        body = chat_completions(
            messages,
            model=model_name,
            temperature=0.1,
            timeout_s=60.0,
            extra={"max_tokens": 1000},
        )
        interpreted_text = extract_message_text(body) or text
        logger.info(f"OpenAI handwriting interpretation: {len(interpreted_text)} chars")
        return interpreted_text.strip()
    except OCRConfigError:
        raise
    except OpenAIChatError as e:
        raise OCRProcessingError(f"OpenAI API failed: {str(e)}") from e
    except Exception as e:
        raise OCRProcessingError(f"OpenAI handwriting interpretation failed: {str(e)}") from e


def _ocr_with_textract(image: Image.Image) -> OCRResult:
    """
    Structured data extraction using AWS Textract.
    Used for lab reports and invoices (tables, structured data).

    Args:
        image: PIL Image object

    Returns:
        OCRResult with structured text

    Raises:
        OCRConfigError: If AWS credentials not configured
        OCRProcessingError: If Textract fails
    """
    start_time = time.time()

    try:
        import boto3

        if not all(
            [
                getattr(settings, "aws_textract_region", None),
                getattr(settings, "aws_textract_access_key_id", None),
                getattr(settings, "aws_textract_secret_access_key", None),
            ]
        ):
            raise OCRConfigError("AWS Textract credentials not configured")

        client = boto3.client(
            "textract",
            region_name=settings.aws_textract_region,
            aws_access_key_id=settings.aws_textract_access_key_id,
            aws_secret_access_key=settings.aws_textract_secret_access_key,
        )

        img_buffer = io.BytesIO()
        image.save(img_buffer, format="PNG")
        img_bytes = img_buffer.getvalue()

        logger.debug("Calling AWS Textract...")
        response = client.detect_document_text(Document={"Bytes": img_bytes})

        extracted_text = ""
        for item in response.get("Blocks", []):
            if item["BlockType"] == "LINE":
                extracted_text += item.get("Text", "") + "\n"

        elapsed = time.time() - start_time
        logger.info(
            f"AWS Textract: extracted {len(extracted_text)} chars (time: {elapsed:.2f}s)"
        )

        return OCRResult(
            text=extracted_text.strip(),
            confidence=0.85,
            provider="textract",
            processing_time=elapsed,
        )

    except OCRConfigError:
        raise
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"AWS Textract failed: {str(e)}")
        raise OCRProcessingError(f"AWS Textract failed: {str(e)}") from e


def _ocr_with_tesseract(image: Image.Image) -> OCRResult:
    """
    Fallback OCR using Tesseract.

    Args:
        image: PIL Image object

    Returns:
        OCRResult with detected text

    Raises:
        OCRConfigError: If Tesseract not installed
        OCRProcessingError: If Tesseract fails
    """
    start_time = time.time()

    try:
        try:
            import pytesseract
        except ImportError as e:
            raise OCRConfigError(
                "Tesseract not installed. Install with: "
                "Linux: apt-get install tesseract-ocr, "
                "macOS: brew install tesseract, "
                "Windows: Download from https://github.com/UB-Mannheim/tesseract"
            ) from e

        if hasattr(settings, "tesseract_cmd_path"):
            pytesseract.pytesseract.pytesseract_cmd = settings.tesseract_cmd_path

        logger.debug("Running Tesseract fallback OCR...")
        try:
            text = pytesseract.image_to_string(image, lang="eng")
        except Exception as e:
            if e.__class__.__name__ == "TesseractNotFoundError":
                raise OCRConfigError(
                    "Tesseract binary not found. Install `tesseract-ocr` and/or set TESSERACT_CMD_PATH."
                ) from e
            raise

        confidence = 0.50 if text.strip() else 0.0

        elapsed = time.time() - start_time
        logger.info(f"Tesseract: extracted {len(text)} chars (time: {elapsed:.2f}s)")

        return OCRResult(
            text=text.strip(),
            confidence=confidence,
            provider="tesseract",
            processing_time=elapsed,
        )

    except OCRConfigError:
        raise
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Tesseract failed: {str(e)}")
        raise OCRProcessingError(f"Tesseract failed: {str(e)}") from e


def run_hybrid_ocr(
    image: Image.Image,
    page_type: Optional[PageType] = None,
    strategy: Optional[str] = None,
) -> OCRResult:
    """
    Run hybrid OCR with automatic provider selection and fallback chain.

    Args:
        image: PIL Image object
        page_type: Classified page type (from page_classifier)
        strategy: Override strategy ("paddle_openai", "textract", "paddle_only", "skip")

    Returns:
        OCRResult with extracted text and metadata

    Raises:
        OCRError: If all OCR methods fail

    Example:
        from app.ai.page_classifier import classify_page, PageType
        from app.ai.ocr_engine import run_hybrid_ocr

        classification = classify_page(image)
        result = run_hybrid_ocr(image, page_type=classification['page_type'])
        print(result.text, result.provider, result.confidence)
    """
    if not strategy and page_type:
        strategy = get_ocr_strategy(page_type)
    strategy = strategy or "paddle_only"

    logger.info(
        f"Running hybrid OCR (strategy: {strategy}, page_type: {page_type.value if page_type else 'unknown'})"
    )

    threshold = float(getattr(settings, "ocr_confidence_threshold", 0.6))

    def needs_fallback(result: OCRResult) -> bool:
        if not result.text.strip():
            return True
        return result.confidence < threshold

    if strategy == "skip":
        logger.debug(f"Skipping OCR for page type: {page_type}")
        return OCRResult(
            text="",
            confidence=0.0,
            provider="skip",
            processing_time=0.0,
            page_type=page_type.value if page_type else None,
            metadata={"reason": f"Page type {page_type} does not require OCR"},
        )

    if strategy == "paddle_openai":
        try:
            paddle_result = _ocr_with_paddleocr(image)
        except (OCRConfigError, OCRProcessingError) as e:
            logger.warning(f"PaddleOCR failed, falling back to Textract: {str(e)}")
            strategy = "textract"
        else:
            try:
                interpreted_text = _ocr_with_openai(paddle_result.text, image)
                result = OCRResult(
                    text=interpreted_text,
                    confidence=paddle_result.confidence,
                    provider="paddle_openai",
                    processing_time=paddle_result.processing_time,
                    page_type=page_type.value if page_type else None,
                    metadata={
                        "pipeline": "paddle→openai",
                        "openai_model": getattr(settings, "openai_vision_model", "gpt-5.1"),
                    },
                )
            except (OCRConfigError, OCRProcessingError) as e:
                # OpenAI unavailable/unconfigured: use PaddleOCR-only text as fallback
                logger.warning(f"OpenAI unavailable; using PaddleOCR text only: {str(e)}")
                result = OCRResult(
                    text=paddle_result.text,
                    confidence=paddle_result.confidence,
                    provider="paddle",
                    processing_time=paddle_result.processing_time,
                    page_type=page_type.value if page_type else None,
                    bounding_boxes=paddle_result.bounding_boxes,
                    metadata={"pipeline": "paddle", "openai": "unavailable"},
                )

            if needs_fallback(result):
                logger.warning(
                    f"Low-confidence OCR (confidence={result.confidence:.2f} < {threshold:.2f}); falling back to Textract"
                )
                strategy = "textract"
            else:
                return result

    if strategy == "textract":
        try:
            textract_result = _ocr_with_textract(image)
            textract_result.page_type = page_type.value if page_type else None
            if needs_fallback(textract_result):
                logger.warning(
                    f"Textract returned low-confidence/empty result; falling back to PaddleOCR (confidence={textract_result.confidence:.2f})"
                )
                strategy = "paddle_only"
            else:
                return textract_result
        except (OCRConfigError, OCRProcessingError) as e:
            logger.warning(f"Textract failed, falling back to PaddleOCR: {str(e)}")
            strategy = "paddle_only"

    if strategy == "paddle_only":
        try:
            paddle_result = _ocr_with_paddleocr(image)
            paddle_result.page_type = page_type.value if page_type else None
            if needs_fallback(paddle_result):
                logger.warning(
                    f"PaddleOCR returned low-confidence/empty result; falling back to Tesseract (confidence={paddle_result.confidence:.2f})"
                )
                strategy = "tesseract"
            else:
                return paddle_result
        except (OCRConfigError, OCRProcessingError) as e:
            logger.warning(f"PaddleOCR failed, falling back to Tesseract: {str(e)}")
            strategy = "tesseract"

    if strategy == "tesseract":
        try:
            tess_result = _ocr_with_tesseract(image)
            tess_result.page_type = page_type.value if page_type else None
            return tess_result
        except (OCRConfigError, OCRProcessingError) as e:
            logger.error(f"All OCR methods failed: {str(e)}")
            if isinstance(e, OCRConfigError):
                raise OCRConfigError(f"All OCR methods unavailable: {str(e)}") from e
            raise OCRProcessingError(f"All OCR methods failed: {str(e)}") from e

    raise OCRError(f"Unknown OCR strategy: {strategy}")
