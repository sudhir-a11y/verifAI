from app.ai.decision_engine import decide_final, final_status_to_decision_recommendation


def test_doctor_override_wins() -> None:
    out = decide_final(
        checklist_result={"recommendation": "reject", "flags": [{"message": "x"}]},
        doctor_verification={"doctor_decision": "approve", "notes": "ok"},
    )
    assert out["final_status"] == "approve"
    assert out["source"] == "doctor_override"
    assert out["reason"] == "ok"


def test_checklist_used_when_no_doctor() -> None:
    out = decide_final(checklist_result={"recommendation": "need_more_evidence"}, doctor_verification=None)
    assert out["final_status"] == "query"
    assert out["source"] == "checklist"


def test_registry_invalid_downgrades_approve_to_query() -> None:
    out = decide_final(
        checklist_result={"recommendation": "approve", "confidence": 0.9},
        doctor_verification=None,
        registry_verifications={"pharmacy_gst_valid": False},
    )
    assert out["final_status"] == "query"
    assert out["source"] == "checklist+registry"
    assert "registry invalid" in out["reason"]


def test_multiple_registry_invalid_rejects() -> None:
    out = decide_final(
        checklist_result={"recommendation": "approve", "confidence": 0.9},
        doctor_verification=None,
        registry_verifications={"hospital_gst_valid": False, "pharmacy_gst_valid": False},
    )
    assert out["final_status"] == "reject"


def test_final_status_to_db_recommendation() -> None:
    assert final_status_to_decision_recommendation("approve") == "approve"
    assert final_status_to_decision_recommendation("reject") == "reject"
    assert final_status_to_decision_recommendation("query") == "need_more_evidence"


def test_ai_decision_override_is_used_when_provided() -> None:
    out = decide_final(
        checklist_result={"recommendation": "approve", "ai_decision": "reject", "ai_confidence": 0.9},
        doctor_verification=None,
        registry_verifications={},
    )
    assert out["ai_decision"] == "reject"
