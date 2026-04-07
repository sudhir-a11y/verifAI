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


def test_final_status_to_db_recommendation() -> None:
    assert final_status_to_decision_recommendation("approve") == "approve"
    assert final_status_to_decision_recommendation("reject") == "reject"
    assert final_status_to_decision_recommendation("query") == "need_more_evidence"

