"""
Unit tests for the doctor verification layer.
"""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.ai.doctor_verification import DoctorVerificationError, verify_doctor_decision


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _structured():
    return {
        "doctor_name": "Dr. Sharma",
        "diagnosis": "Viral fever",
        "medicines": ["Tab PCM 650"],
        "duration": "3 days",
        "hospital": "City Hospital",
        "date": "2025-01-15",
    }


def _checklist(**overrides):
    base = {"flags": [], "severity": "pass", "recommendation": "APPROVE", "confidence": 0.95}
    base.update(overrides)
    return base


def _flag(field, code, msg, severity="warning"):
    return {"field": field, "code": code, "message": msg, "severity": severity}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestVerifyDoctorDecisionHappyPath:
    def test_approve_no_edits(self):
        result = verify_doctor_decision(
            structured=_structured(),
            checklist=_checklist(),
            doctor_id="dr_sharma",
            decision="approve",
        )
        assert result["doctor_decision"] == "approve"
        assert result["notes"] == ""
        assert result["edited_fields"] == {}
        assert result["flags_overridden"] is False
        assert result["doctor_id"] == "dr_sharma"
        assert "reviewed_at" in result
        assert result["confidence"] > 0.8

    def test_approve_with_edits(self):
        result = verify_doctor_decision(
            structured=_structured(),
            checklist=_checklist(),
            doctor_id="dr_patil",
            decision="approve",
            notes="Corrected diagnosis from records",
            edited_fields={"diagnosis": "Dengue fever"},
        )
        assert result["doctor_decision"] == "approve"
        assert result["edited_fields"] == {"diagnosis": "Dengue fever"}
        assert "dengue" in result["verified_data"]["diagnosis"].lower()
        assert result["flags_overridden"] is False

    def test_reject(self):
        result = verify_doctor_decision(
            structured=_structured(),
            checklist=_checklist(),
            doctor_id="dr_kumar",
            decision="reject",
            notes="Forged prescription",
        )
        assert result["doctor_decision"] == "reject"
        assert "forged" in result["notes"].lower()


# ---------------------------------------------------------------------------
# Decision normalization
# ---------------------------------------------------------------------------


class TestDecisionNormalization:
    def test_approved_maps_to_approve(self):
        result = verify_doctor_decision(_structured(), _checklist(), doctor_id="d1", decision="approved")
        assert result["doctor_decision"] == "approve"

    def test_accept_maps_to_approve(self):
        result = verify_doctor_decision(_structured(), _checklist(), doctor_id="d1", decision="accept")
        assert result["doctor_decision"] == "approve"

    def test_denied_maps_to_reject(self):
        result = verify_doctor_decision(_structured(), _checklist(), doctor_id="d1", decision="denied")
        assert result["doctor_decision"] == "reject"

    def test_pending_maps_to_query(self):
        result = verify_doctor_decision(_structured(), _checklist(), doctor_id="d1", decision="pending")
        assert result["doctor_decision"] == "query"

    def test_invalid_raises(self):
        with pytest.raises(DoctorVerificationError):
            verify_doctor_decision(_structured(), _checklist(), doctor_id="d1", decision="foobar")

    def test_missing_doctor_id_raises(self):
        with pytest.raises(DoctorVerificationError):
            verify_doctor_decision(_structured(), _checklist(), doctor_id="", decision="approve")


# ---------------------------------------------------------------------------
# Flag override detection
# ---------------------------------------------------------------------------


class TestFlagOverride:
    def test_doctor_edits_flagged_field(self):
        result = verify_doctor_decision(
            structured=_structured(),
            checklist=_checklist(flags=[_flag("diagnosis", "SHORT_DIAGNOSIS", "Diagnosis very short", severity="warning")]),
            doctor_id="d1",
            decision="approve",
            edited_fields={"diagnosis": "Confirmed dengue fever with thrombocytopenia"},
        )
        assert result["flags_overridden"] is True

    def test_doctor_edits_non_flagged_field(self):
        result = verify_doctor_decision(
            structured=_structured(),
            checklist=_checklist(flags=[_flag("hospital", "MISSING_HOSPITAL", "Hospital missing", severity="critical")]),
            doctor_id="d1",
            decision="approve",
            edited_fields={"duration": "5 days"},
        )
        assert result["flags_overridden"] is False

    def test_no_flags(self):
        result = verify_doctor_decision(
            structured=_structured(),
            checklist=_checklist(),
            doctor_id="d1",
            decision="approve",
            edited_fields={"diagnosis": "Updated"},
        )
        assert result["flags_overridden"] is False


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------


class TestConfidenceScoring:
    def test_approved_with_fixes_high_confidence(self):
        result = verify_doctor_decision(
            structured=_structured(),
            checklist=_checklist(flags=[_flag("diagnosis", "SHORT_DIAGNOSIS", "Short", severity="warning")]),
            doctor_id="d1",
            decision="approve",
            edited_fields={"diagnosis": "Dengue with complications"},
        )
        assert result["confidence"] > 0.7

    def test_query_lower_confidence(self):
        result = verify_doctor_decision(
            structured=_structured(),
            checklist=_checklist(),
            doctor_id="d1",
            decision="query",
        )
        # Query should have lower confidence than approve with same data
        approve_result = verify_doctor_decision(
            _structured(), _checklist(), doctor_id="d1", decision="approve",
        )
        assert result["confidence"] < approve_result["confidence"]

    def test_reject_reflects_data_quality(self):
        result = verify_doctor_decision(
            structured=_structured(),
            checklist=_checklist(),
            doctor_id="d1",
            decision="reject",
            notes="Document appears forged",
        )
        # Rejection confidence reflects data quality
        assert 0.0 <= result["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_structured(self):
        result = verify_doctor_decision({}, _checklist(), doctor_id="d1", decision="approve")
        assert result["doctor_decision"] == "approve"
        assert result["verified_data"]["doctor_name"] == ""

    def test_none_structured(self):
        result = verify_doctor_decision(None, _checklist(), doctor_id="d1", decision="approve")  # type: ignore
        assert result["doctor_decision"] == "approve"

    def test_invalid_edit_key_ignored(self):
        result = verify_doctor_decision(
            _structured(),
            _checklist(),
            doctor_id="d1",
            decision="approve",
            edited_fields={"invalid_key": "should be dropped"},
        )
        assert "invalid_key" not in result["edited_fields"]
        assert "invalid_key" not in result["verified_data"]

    def test_medicines_list_cleaned(self):
        result = verify_doctor_decision(
            _structured(),
            _checklist(),
            doctor_id="d1",
            decision="approve",
            edited_fields={"medicines": ["  Tab PCM  ", "  Cap Amoxil  "]},
        )
        assert result["verified_data"]["medicines"] == ["Tab PCM", "Cap Amoxil"]

    def test_notes_truncated(self):
        long_note = "x" * 5000
        result = verify_doctor_decision(
            _structured(), _checklist(), doctor_id="d1", decision="approve", notes=long_note,
        )
        assert len(result["notes"]) <= 2000
