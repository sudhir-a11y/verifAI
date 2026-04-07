from app.ai.provider_verifications import (
    extract_hospital_gstin,
    extract_hospital_name,
    extract_pharmacy_drug_license,
    extract_pharmacy_gstin,
    extract_pharmacy_name,
    gst_verify,
    hospital_gst_verify,
)


def test_pharmacy_extraction_from_entity_docs() -> None:
    structured = {
        "hospital_name": "ABC Hospital",
        "raw_payload": {
            "context": {
                "legacy": {"hospital_state": "Maharashtra"},
                "entity_docs": [
                    {
                        "hospital_gstin": "27AAAAA0000A1Z5",
                        "pharmacy_name": "ABC Medical Store",
                        "gstin": "27AAPFU0939F1ZV",
                        "drug_license_no": "20B/123-456",
                    }
                ],
                "evidence_lines": [],
            }
        }
    }

    assert extract_hospital_name(structured) == "ABC Hospital"
    assert extract_hospital_gstin(structured) == "27AAAAA0000A1Z5"
    assert extract_pharmacy_name(structured) == "ABC Medical Store"
    assert extract_pharmacy_gstin(structured) == "27AAPFU0939F1ZV"
    assert extract_pharmacy_drug_license(structured) == "20B/123-456"


def test_gst_verify_best_effort_basic_when_provider_disabled() -> None:
    structured = {
        "hospital_name": "Some Hospital",
        "raw_payload": {
            "context": {
                "legacy": {"pharmacy_name": "ABC Medical Store", "hospital_state": "Maharashtra"},
                "entity_docs": [{"gstin": "27AAPFU0939F1ZV"}],
                "evidence_lines": [],
            }
        }
    }
    out = gst_verify(structured)
    assert out is not None
    assert out["valid"] is True


def test_hospital_gst_verify_best_effort_basic_when_provider_disabled() -> None:
    structured = {
        "hospital_name": "ABC Hospital",
        "raw_payload": {
            "context": {
                "legacy": {"hospital_state": "Maharashtra"},
                "entity_docs": [{"hospital_gstin": "27AAPFU0939F1ZV"}],
                "evidence_lines": [],
            }
        },
    }
    out = hospital_gst_verify(structured)
    assert out is not None
    assert out["valid"] is True
