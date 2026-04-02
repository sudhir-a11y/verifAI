from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class ChecklistDecision(str, Enum):
    approve = "APPROVE"
    query = "QUERY"
    reject = "REJECT"


class ChecklistRunRequest(BaseModel):
    actor_id: str | None = Field(default=None, max_length=100)
    force_source_refresh: bool = False


class ChecklistEntry(BaseModel):
    code: str
    name: str
    decision: ChecklistDecision
    severity: str
    source: str
    matched_scope: bool
    triggered: bool
    status: str
    missing_evidence: list[str] = Field(default_factory=list)
    note: str


class ChecklistRunResponse(BaseModel):
    claim_id: UUID
    decision_result_id: UUID
    recommendation: str
    route_target: str
    manual_review_required: bool
    review_priority: int
    generated_at: datetime
    checklist: list[ChecklistEntry]
    source_summary: dict


class ChecklistLatestResponse(BaseModel):
    found: bool
    claim_id: UUID
    decision_result_id: UUID | None = None
    recommendation: str | None = None
    route_target: str | None = None
    manual_review_required: bool | None = None
    review_priority: int | None = None
    generated_at: datetime | None = None
    checklist: list[ChecklistEntry] = Field(default_factory=list)
    source_summary: dict = Field(default_factory=dict)


class DiagnosisChecklistTemplateRequest(BaseModel):
    diagnosis: str | None = Field(default=None, max_length=255)
    actor_id: str | None = Field(default=None, max_length=100)
    force_refresh: bool = False


class DiagnosisChecklistReference(BaseModel):
    title: str = ""
    url: str = ""


class DiagnosisChecklistTemplateResponse(BaseModel):
    claim_id: UUID
    diagnosis_key: str
    diagnosis_name: str
    symptoms: list[str] = Field(default_factory=list)
    drug_choices: list[str] = Field(default_factory=list)
    investigation_findings: list[str] = Field(default_factory=list)
    caution_notes: str = ""
    references: list[DiagnosisChecklistReference] = Field(default_factory=list)
    source: str = ""
    model_name: str | None = None
    generated_at: datetime | None = None
    from_cache: bool = False
    criteria_id: str | None = None
