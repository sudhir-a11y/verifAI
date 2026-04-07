from app.domain.integrations.gst_use_cases import (
    extract_gstin,
    gst_state_code_from_state_name,
    is_valid_gstin,
    verify_gstin_best_effort,
)


def test_extract_gstin() -> None:
    assert extract_gstin("GSTIN: 27AAPFU0939F1ZV") == "27AAPFU0939F1ZV"


def test_gstin_checksum_valid_and_invalid() -> None:
    assert is_valid_gstin("27AAPFU0939F1ZV") is True
    assert is_valid_gstin("27AAPFU0939F1ZA") is False


def test_verify_gstin_best_effort() -> None:
    assert verify_gstin_best_effort("27AAPFU0939F1ZV")["valid"] is True
    assert verify_gstin_best_effort("27AAPFU0939F1ZA")["valid"] is False


def test_gst_state_code_from_name_basic() -> None:
    assert gst_state_code_from_state_name("Delhi") == "07"
    assert gst_state_code_from_state_name("Karnataka") == "29"
