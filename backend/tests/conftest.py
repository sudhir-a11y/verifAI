"""
Pytest configuration for VerifAI backend tests.
"""

import sys
from pathlib import Path

import pytest

# Add backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


@pytest.fixture
def sample_pdf_path():
    """Return path to a sample PDF file for testing."""
    test_dir = Path(__file__).parent / "fixtures"
    test_dir.mkdir(exist_ok=True)
    return test_dir / "sample.pdf"


@pytest.fixture
def blank_pdf_path():
    """Return path to a blank PDF file for testing."""
    test_dir = Path(__file__).parent / "fixtures"
    test_dir.mkdir(exist_ok=True)
    return test_dir / "blank.pdf"
