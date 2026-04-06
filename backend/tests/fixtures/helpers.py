"""
Helper utilities for generating test fixtures.
Creates sample PDFs and images for testing.
"""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def create_sample_pdf_with_reportlab(
    pages: list[dict], output_path: Path
) -> Path:
    """
    Create a sample PDF with text content on each page using ReportLab.

    Args:
        pages: List of dicts with 'text' and optionally 'title'
        output_path: Where to save the PDF

    Returns:
        Path to created PDF
    """
    c = canvas.Canvas(str(output_path), pagesize=letter)
    width, height = letter

    for page_data in pages:
        y = height - 50

        # Draw title
        if title := page_data.get("title"):
            c.setFont("Helvetica-Bold", 16)
            c.drawString(50, y, title)
            y -= 30

        # Draw text content
        c.setFont("Helvetica", 12)
        text = page_data.get("text", "")
        for line in text.split("\n"):
            if y < 50:
                break
            c.drawString(50, y, line)
            y -= 20

        c.showPage()

    c.save()
    return output_path


def create_multi_page_pdf(
    pages: list[dict], output_path: Path
) -> Path:
    """Create a multi-page PDF (alias for create_sample_pdf_with_reportlab)."""
    return create_sample_pdf_with_reportlab(pages, output_path)


def create_blank_pdf_with_reportlab(output_path: Path) -> Path:
    """Create a blank PDF with no content."""
    c = canvas.Canvas(str(output_path), pagesize=letter)
    c.showPage()
    c.save()
    return output_path


def create_sample_image(
    text: str = "Sample prescription",
    width: int = 800,
    height: int = 1100,
    output_path: Path | None = None,
) -> Image.Image:
    """Create a sample image with text for testing."""
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
    except Exception:
        font = ImageFont.load_default()

    draw.text((100, 100), text, font=font, fill="black")

    if output_path:
        img.save(output_path)

    return img


def create_prescription_image(output_path: Path | None = None) -> Image.Image:
    """Create a realistic prescription image for testing."""
    img = Image.new("RGB", (800, 1100), "white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
    except Exception:
        font = ImageFont.load_default()
        title_font = font

    y = 50
    draw.text((50, y), "MEDICAL PRESCRIPTION", font=title_font, fill="black")
    y += 60

    lines = [
        "Dr. John Smith, MBBS, MD",
        "Registration No: 12345",
        "Specialization: General Medicine",
        "",
        "Patient: Jane Doe",
        "Date: 2026-04-06",
        "",
        "Rx:",
        "1. Amoxicillin 500mg - TDS for 5 days",
        "2. Paracetamol 650mg - SOS",
        "3. Vitamin C 500mg - OD for 10 days",
        "",
        "Follow-up after 7 days",
    ]

    for line in lines:
        draw.text((50, y), line, font=font, fill="black")
        y += 35

    if output_path:
        img.save(output_path)

    return img


def create_lab_report_image(output_path: Path | None = None) -> Image.Image:
    """Create a realistic lab report image for testing."""
    img = Image.new("RGB", (800, 1100), "white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
    except Exception:
        font = ImageFont.load_default()
        title_font = font

    y = 50
    draw.text((50, y), "LABORATORY TEST REPORT", font=title_font, fill="black")
    y += 60

    lines = [
        "Patient: John Doe",
        "Date: 2026-04-06",
        "Lab ID: LAB-2026-001",
        "",
        "Test Results:",
        "Hemoglobin: 14.5 g/dL (Normal: 13.5-17.5)",
        "WBC Count: 7,500/cumm (Normal: 4,000-11,000)",
        "Platelet Count: 2,50,000/cumm (Normal: 1,50,000-4,50,000)",
        "Blood Sugar (Fasting): 95 mg/dL (Normal: 70-100)",
        "Blood Sugar (PP): 130 mg/dL (Normal: <140)",
        "",
        "All values within normal limits.",
    ]

    for line in lines:
        draw.text((50, y), line, font=font, fill="black")
        y += 35

    if output_path:
        img.save(output_path)

    return img


def create_invoice_image(output_path: Path | None = None) -> Image.Image:
    """Create a realistic invoice/bill image for testing."""
    img = Image.new("RGB", (800, 1100), "white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        header_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
        title_font = font
        header_font = font

    y = 50
    draw.text((50, y), "HOSPITAL BILL", font=title_font, fill="black")
    y += 60

    lines = [
        "Patient: Jane Doe",
        "Bill No: BILL-2026-001",
        "Date: 2026-04-06",
        "",
    ]

    for line in lines:
        draw.text((50, y), line, font=font, fill="black")
        y += 35

    # Table header
    draw.text((50, y), "Description", font=header_font, fill="black")
    draw.text((400, y), "Amount", font=header_font, fill="black")
    y += 40

    items = [
        ("Room Charges (3 days)", "3,000"),
        ("Doctor Consultation", "1,500"),
        ("Medicines", "2,200"),
        ("Lab Tests", "1,800"),
        ("Nursing Charges", "800"),
    ]

    for desc, amt in items:
        draw.text((50, y), desc, font=font, fill="black")
        draw.text((400, y), f"Rs. {amt}", font=font, fill="black")
        y += 35

    y += 20
    draw.text((50, y), "Total Amount:", font=header_font, fill="black")
    draw.text((400, y), "Rs. 9,300", font=header_font, fill="black")

    if output_path:
        img.save(output_path)

    return img
