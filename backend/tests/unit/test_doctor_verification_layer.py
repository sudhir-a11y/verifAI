from app.ai.doctor_verification import run_doctor_verification


def test_run_doctor_verification_contract() -> None:
    out = run_doctor_verification(
        {"treating_doctor": "Dr A", "diagnosis": "fever", "medicine_used": "pcm", "hospital_name": "H"},
        {"flags": [{"field": "diagnosis", "severity": "warning"}], "recommendation": "QUERY"},
        doctor_decision="approve",
        notes="ok",
        edited_fields={"diagnosis": "viral fever"},
        doctor_id="dr_a",
    )
    assert set(out.keys()) == {"doctor_decision", "notes", "edited_fields", "confidence"}
    assert out["doctor_decision"] == "approve"
    assert out["notes"] == "ok"
    assert out["edited_fields"]["diagnosis"] == "viral fever"
    assert 0.0 <= float(out["confidence"]) <= 1.0

