from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DoctorVerificationSubmitRequest(BaseModel):
    doctor_decision: str = Field(min_length=1, max_length=30)
    notes: str = Field(default="", max_length=2000)
    edited_fields: dict = Field(default_factory=dict)
    auto_generate_structured: bool = False
    use_llm: bool = False


class DoctorVerificationResponse(BaseModel):
    id: int
    claim_id: UUID
    doctor_id: str | None = None
    doctor_decision: str
    notes: str
    edited_fields: dict = Field(default_factory=dict)
    verified_data: dict = Field(default_factory=dict)
    checklist_result: dict = Field(default_factory=dict)
    confidence: float
    reviewed_at: datetime

