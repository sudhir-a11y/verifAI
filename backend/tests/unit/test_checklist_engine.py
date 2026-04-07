"""
Unit tests for Phase 1 checklist engine (structured data validation).
"""

from datetime import date, timedelta
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.ai.checklist_engine import (
    check_date,
    check_diagnosis,
    check_doctor_name,
    check_medicines,
    run_checklist,
)


# ---------------------------------------------------------------------------
# run_checklist — happy path
# ---------------------------------------------------------------------------


class TestRunChecklistHappyPath:
    def test_all_present(self):
        data = {
            "doctor_name": "Dr. Sharma",
            "diagnosis": "Viral fever",
            "medicines": ["Tab PCM 650", "Syrup Benadryl 10ml"],
            "duration": "3 days",
            "hospital": "City Hospital",
            "date": "2025-01-15",
        }
        result = run_checklist(data)
        assert result["severity"] == "low"
        assert result["recommendation"] == "APPROVE"
        assert result["flags"] == []
        assert result["confidence"] > 0.9

    def test_minimum_valid(self):
        data = {
            "doctor_name": "Dr. Patil",
            "diagnosis": "Cold",
            "medicines": ["Tab Crocin"],
            "duration": "",
            "hospital": "Clinic A",
            "date": "2025-03-01",
        }
        result = run_checklist(data)
        assert result["severity"] in ("low", "medium")
        assert result["confidence"] > 0.5


# ---------------------------------------------------------------------------
# run_checklist — missing fields
# ---------------------------------------------------------------------------


class TestRunChecklistMissingFields:
    def test_empty_input(self):
        result = run_checklist({})
        assert result["severity"] == "high"
        assert result["recommendation"] in ("QUERY", "REJECT")
        assert len(result["flags"]) >= 4  # at least doctor, diagnosis, medicines, hospital

    def test_none_input(self):
        result = run_checklist(None)  # type: ignore[arg-type]
        assert result["severity"] == "high"
        assert result["confidence"] < 0.1

    def test_missing_doctor(self):
        data = _good_data(doctor_name="")
        result = run_checklist(data)
        assert any(f["code"] == "MISSING_DOCTOR" for f in result["flags"])

    def test_missing_diagnosis(self):
        data = _good_data(diagnosis="")
        result = run_checklist(data)
        assert any(f["code"] == "MISSING_DIAGNOSIS" for f in result["flags"])

    def test_missing_medicines(self):
        data = _good_data(medicines=[])
        result = run_checklist(data)
        assert any(f["code"] == "MISSING_MEDICINES" for f in result["flags"])

    def test_missing_hospital(self):
        data = _good_data(hospital="")
        result = run_checklist(data)
        assert any(f["code"] == "MISSING_HOSPITAL" for f in result["flags"])

    def test_missing_date(self):
        data = _good_data(date="")
        result = run_checklist(data)
        assert any(f["code"] == "MISSING_DATES" for f in result["flags"])

    def test_many_missing_rejects(self):
        # multiple missing critical fields -> reject
        data = {"doctor_name": "", "diagnosis": "", "medicines": [], "hospital": "", "date": "", "duration": ""}
        result = run_checklist(data)
        assert result["recommendation"] == "REJECT"

    def test_disable_required(self):
        data = {"doctor_name": "", "diagnosis": "fever", "medicines": [], "hospital": "", "date": "", "duration": ""}
        result = run_checklist(data, require_doctor=False, require_medicines=False)
        # Should have fewer flags now
        missing_codes = {f["code"] for f in result["flags"]}
        assert "MISSING_DOCTOR" not in missing_codes
        assert "MISSING_MEDICINES" not in missing_codes


# ---------------------------------------------------------------------------
# run_checklist — quality checks
# ---------------------------------------------------------------------------


class TestRunChecklistQuality:
    def test_placeholder_doctor(self):
        data = _good_data(doctor_name="unknown")
        result = run_checklist(data)
        assert any(f["code"] == "INVALID_DOCTOR_NAME" for f in result["flags"])

    def test_future_date(self):
        future = (date.today() + timedelta(days=30)).isoformat()
        data = _good_data(date=future)
        result = run_checklist(data)
        assert any(f["code"] == "FUTURE_DATE" for f in result["flags"])
        assert result["severity"] == "high"

    def test_very_old_date(self):
        data = _good_data(date="1990-01-01")
        result = run_checklist(data)
        assert any(f["code"] == "VERY_OLD_DATE" for f in result["flags"])

    def test_short_diagnosis(self):
        data = _good_data(diagnosis="X")
        result = run_checklist(data)
        assert any(f["code"] == "SHORT_DIAGNOSIS" for f in result["flags"])

    def test_placeholder_medicine(self):
        data = _good_data(medicines=["N/A", "Tab PCM"])
        result = run_checklist(data)
        assert any(f["code"] == "INVALID_MEDICINE_ENTRY" for f in result["flags"])


# ---------------------------------------------------------------------------
# Individual field validators
# ---------------------------------------------------------------------------


class TestCheckDoctorName:
    def test_valid(self):
        assert check_doctor_name("Dr. Ramesh Gupta") == []

    def test_short(self):
        flags = check_doctor_name("Dr X")
        assert any(f["code"] == "SHORT_DOCTOR_NAME" for f in flags)

    def test_placeholder(self):
        flags = check_doctor_name("not found")
        assert any(f["code"] == "INVALID_DOCTOR_NAME" for f in flags)

    def test_suspicious_chars(self):
        flags = check_doctor_name("Dr. Sh@rma")
        assert any(f["code"] == "SUSPICIOUS_DOCTOR_NAME" for f in flags)


class TestCheckDiagnosis:
    def test_valid(self):
        assert check_diagnosis("Type 2 diabetes mellitus") == []

    def test_short(self):
        flags = check_diagnosis("A")
        assert any(f["code"] == "SHORT_DIAGNOSIS" for f in flags)

    def test_long(self):
        flags = check_diagnosis("Lorem ipsum " * 20)
        assert any(f["code"] == "LONG_DIAGNOSIS" for f in flags)

    def test_placeholder(self):
        flags = check_diagnosis("unknown")
        assert any(f["code"] == "INVALID_DIAGNOSIS" for f in flags)


class TestCheckMedicines:
    def test_valid_list(self):
        assert check_medicines(["Tab PCM", "Cap Amoxil"]) == []

    def test_placeholder_entry(self):
        flags = check_medicines(["blank", "Tab PCM"])
        assert any(f["code"] == "INVALID_MEDICINE_ENTRY" for f in flags)

    def test_short_entry(self):
        flags = check_medicines(["X"])
        assert any(f["code"] == "SHORT_MEDICINE_ENTRY" for f in flags)

    def test_not_a_list(self):
        flags = check_medicines("not a list")  # type: ignore[arg-type]
        assert any(f["code"] == "INVALID_MEDICINES_FORMAT" for f in flags)

    def test_empty_list(self):
        assert check_medicines([]) == []


class TestCheckDate:
    def test_valid(self):
        today_str = date.today().isoformat()
        assert check_date(today_str) == []

    def test_future(self):
        future = (date.today() + timedelta(days=10)).isoformat()
        flags = check_date(future)
        assert any(f["code"] == "FUTURE_DATE" for f in flags)

    def test_very_old(self):
        flags = check_date("1980-06-15")
        assert any(f["code"] == "VERY_OLD_DATE" for f in flags)

    def test_bad_format(self):
        flags = check_date("2025-02")  # missing day
        assert any(f["code"] == "INVALID_DATE_FORMAT" for f in flags)

    def test_invalid_date(self):
        flags = check_date("2025-13-45")
        assert any(f["code"] == "INVALID_DATE" for f in flags)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _good_data(**overrides):
    today = (date.today() - timedelta(days=7)).isoformat()
    base = {
        "doctor_name": "Dr. Sharma",
        "diagnosis": "Viral fever",
        "medicines": ["Tab PCM 650"],
        "duration": "3 days",
        "hospital": "City Hospital",
        "date": today,
    }
    base.update(overrides)
    return base
