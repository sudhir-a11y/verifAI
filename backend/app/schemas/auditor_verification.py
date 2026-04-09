from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AuditorVerificationSubmitRequest(BaseModel):
    auditor_decision: str = Field(min_length=1, max_length=30)
    notes: str = Field(default="", max_length=2000)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class AuditorVerificationResponse(BaseModel):
    id: int
    claim_id: UUID
    auditor_id: str | None = None
    auditor_decision: str
    notes: str
    confidence: float
    reviewed_at: datetime

