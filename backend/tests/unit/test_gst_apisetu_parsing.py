from app.core.config import settings
from app.domain.integrations import gst_use_cases


def test_verify_gstin_via_apisetu_parses_common_taxpayer_payload(monkeypatch) -> None:
    sample = {
        "gstIdentificationNumber": "09AAACO4007A1Z3",
        "gstnStatus": "Active",
        "tradeName": "M/S ONE 97 COMMUNICATION LTD",
        "legalNameOfBusiness": "ONE97 COMMUNICATIONS LIMITED",
        "principalPlaceOfBusinessFields": {
            "principalPlaceOfBusinessAddress": {"stateName": "Uttar Pradesh"}
        },
    }

    monkeypatch.setattr(gst_use_cases, "fetch_taxpayer_details", lambda gstin: sample)
    monkeypatch.setattr(settings, "apisetu_gst_enabled", True)

    out = gst_use_cases.verify_gstin_via_apisetu_best_effort(
        gstin="09AAACO4007A1Z3",
        expected_name="ONE97 COMMUNICATIONS LIMITED",
        expected_state="Uttar Pradesh",
    )
    assert out["source"] == "apisetu"
    assert out["valid"] is True
    assert out["status"] == "active"
    assert out["legal_name"] == "ONE97 COMMUNICATIONS LIMITED"
    assert out["trade_name"]
    assert out["state_name"] == "Uttar Pradesh"

