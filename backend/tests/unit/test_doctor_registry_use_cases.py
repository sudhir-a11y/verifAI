from app.domain.integrations.doctor_registry_use_cases import verify_doctor_registration_from_candidates


def test_doctor_registry_match_happy_path() -> None:
    out = verify_doctor_registration_from_candidates(
        name="Dr ABC",
        registration_number="12345",
        state="Delhi",
        candidates=[
            {
                "name": "Dr. A B C",
                "registrationCouncil": "Delhi Medical Council",
                "registrationStatus": "Active",
                "speciality": "Medicine",
            }
        ],
    )
    assert out["valid"] is True
    assert out["status"] == "active"
    assert "Delhi" in out["council"]


def test_doctor_registry_mismatch_state_is_invalid() -> None:
    out = verify_doctor_registration_from_candidates(
        name="Dr ABC",
        registration_number="12345",
        state="Karnataka",
        candidates=[
            {
                "name": "Dr ABC",
                "registrationCouncil": "Delhi Medical Council",
                "registrationStatus": "Active",
            }
        ],
    )
    assert out["valid"] is False
    assert out["doctor_name"]


def test_doctor_registry_not_found() -> None:
    out = verify_doctor_registration_from_candidates(
        name="Dr ABC",
        registration_number="12345",
        state="Delhi",
        candidates=[],
    )
    assert out["valid"] is False
    assert out["status"] == "not_found"

