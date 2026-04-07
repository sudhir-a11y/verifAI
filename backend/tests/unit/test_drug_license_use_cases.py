from app.domain.integrations.drug_license_use_cases import (
    extract_drug_license,
    is_plausible_drug_license,
    verify_drug_license_best_effort,
)


def test_extract_drug_license() -> None:
    assert extract_drug_license("DL No: 20B/123-456") == "20B/123-456"


def test_drug_license_plausibility() -> None:
    assert is_plausible_drug_license("20B/123-456") is True
    assert is_plausible_drug_license("ABCDE") is False
    assert is_plausible_drug_license("000000") is False


def test_verify_drug_license_best_effort() -> None:
    assert verify_drug_license_best_effort("20B/123-456")["valid"] is True
    assert verify_drug_license_best_effort("ABCDE")["valid"] is False
