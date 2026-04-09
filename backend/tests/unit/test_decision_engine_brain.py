from __future__ import annotations


def test_ai_auto_approve_low_risk():
    from app.ai.decision_engine import decide_final

    checklist = {"recommendation": "APPROVE", "confidence": 0.8, "flags": []}
    final = decide_final(
        checklist_result=checklist,
        doctor_verification=None,
        registry_verifications={},
        structured_data={"claim_amount": "5000"},
    )

    assert final["final_status"] == "approve"
    assert final["final_status_mapping"] == "auto_approve"
    assert final["route_target"] == "auto_approve_queue"


def test_ai_approve_with_both_gst_invalid_rejects():
    from app.ai.decision_engine import decide_final

    checklist = {"recommendation": "APPROVE", "confidence": 0.7, "flags": []}
    verifications = {"hospital_gst_valid": False, "pharmacy_gst_valid": False}
    final = decide_final(
        checklist_result=checklist,
        doctor_verification=None,
        registry_verifications=verifications,
        structured_data={"claim_amount": "8000"},
    )

    assert final["final_status"] == "reject"
    assert any("gst" in str(x.get("code") or "").lower() for x in final["risk_breakdown"])


def test_doctor_approve_high_risk_routes_for_review():
    from app.ai.decision_engine import decide_final

    checklist = {"recommendation": "APPROVE", "confidence": 0.75, "flags": []}
    doctor_verification = {"doctor_decision": "approve", "notes": "ok", "confidence": 0.9}
    verifications = {"doctor_valid": False, "hospital_gst_valid": False}
    final = decide_final(
        checklist_result=checklist,
        doctor_verification=doctor_verification,
        registry_verifications=verifications,
        structured_data={"claim_amount": "300000"},
    )

    assert final["final_status"] == "query"
    assert final["risk_score"] >= 0.7
    assert final["final_status_mapping"] in {"auditor_review", "manual_review", "doctor_review"}


def test_conflict_ai_approve_doctor_reject_detected():
    from app.ai.decision_engine import decide_final

    checklist = {"recommendation": "APPROVE", "confidence": 0.8, "flags": []}
    doctor_verification = {"doctor_decision": "reject", "notes": "bad", "confidence": 0.8}
    final = decide_final(
        checklist_result=checklist,
        doctor_verification=doctor_verification,
        registry_verifications={},
        structured_data={"claim_amount": "10000"},
    )

    conflict_types = {c.get("type") for c in final.get("conflicts") or []}
    assert "ai_vs_doctor" in conflict_types


def test_auditor_override_beats_doctor():
    from app.ai.decision_engine import decide_final

    checklist = {"recommendation": "REJECT", "confidence": 0.6, "flags": []}
    doctor_verification = {"doctor_decision": "reject", "notes": "reject", "confidence": 0.85}
    auditor_verification = {"auditor_decision": "approve", "notes": "approved", "confidence": 0.9}
    final = decide_final(
        checklist_result=checklist,
        doctor_verification=doctor_verification,
        auditor_verification=auditor_verification,
        registry_verifications={},
        structured_data={"claim_amount": "20000"},
    )

    assert final["final_status"] == "approve"
    assert final["source"] == "auditor_override"

