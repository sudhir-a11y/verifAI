from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TeamRightWorksCaseIntakeRequest(BaseModel):
    external_claim_id: str = Field(min_length=1, max_length=100)
    patient_name: str | None = Field(default=None, max_length=255)
    patient_identifier: str | None = Field(default=None, max_length=100)
    assigned_doctor_id: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, max_length=40)
    priority: int = Field(default=3, ge=1, le=5)
    source_channel: str | None = Field(default="teamrightworks.in", max_length=100)
    tags: list[str] | None = None

    legacy_payload: dict[str, Any] | None = None
    raw_files_only: bool = False

    report_html: str | None = None
    report_status: str = Field(default="completed", max_length=30)
    doctor_username: str | None = Field(default=None, max_length=100)
    doctor_opinion: str | None = Field(default=None, max_length=20000)
    tagging: str | None = Field(default=None, max_length=120)
    subtagging: str | None = Field(default=None, max_length=240)
    opinion: str | None = Field(default=None, max_length=20000)
    report_export_status: str | None = Field(default=None, max_length=30)
    qc_status: str | None = Field(default=None, max_length=10)

    recommendation: str | None = Field(default=None, max_length=40)
    explanation_summary: str | None = Field(default=None, max_length=20000)
    decision_payload: dict[str, Any] | None = None

    auditor_label: str | None = Field(default=None, max_length=40)
    auditor_notes: str | None = Field(default=None, max_length=4000)

    event_occurred_at: datetime | None = None
    sync_ref: str | None = Field(default=None, max_length=160)


class TeamRightWorksCaseIntakeResponse(BaseModel):
    ok: bool = True
    claim_id: str
    external_claim_id: str
    created_claim: bool
    report_version_no: int | None = None
    decision_id: str | None = None
    feedback_label_saved: bool = False
    message: str


# ────────────────────────────────────────────────────────────────────
# ABDM HPR (Healthcare Professionals Registry) schemas
# ────────────────────────────────────────────────────────────────────

class AbdmHprDoctorVerificationResponse(BaseModel):
    """Response model for ABDM HPR doctor verification."""

    hpr_id: str = Field(max_length=100)
    name: str = Field(max_length=255)
    registration_number: str = Field(default="", max_length=100)
    status: str = Field(default="Unknown", max_length=50)
    qualifications: list[str] = Field(default_factory=list)
    speciality: str | None = Field(default=None, max_length=200)
    verified: bool = True
    message: str = Field(default="Doctor verified successfully", max_length=500)


class AbdmHprDoctorSearchRequest(BaseModel):
    """Request model for searching doctors by registration number."""

    registration_number: str = Field(min_length=1, max_length=100)


class AbdmHprDoctorSearchResult(BaseModel):
    """Single result from an ABDM HPR doctor search."""

    hpr_id: str = Field(max_length=100)
    name: str = Field(max_length=255)
    registration_number: str = Field(max_length=100)
    status: str = Field(max_length=50)
    speciality: str | None = None


class AbdmHprDoctorSearchResponse(BaseModel):
    """Response model for ABDM HPR doctor search."""

    total: int
    items: list[AbdmHprDoctorSearchResult]


