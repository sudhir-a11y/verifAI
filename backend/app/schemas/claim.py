from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class ClaimStatus(str, Enum):
    ready_for_assignment = "ready_for_assignment"
    waiting_for_documents = "waiting_for_documents"
    in_review = "in_review"
    needs_qc = "needs_qc"
    completed = "completed"
    withdrawn = "withdrawn"


class CreateClaimRequest(BaseModel):
    external_claim_id: str = Field(min_length=1, max_length=100)
    patient_name: str | None = Field(default=None, max_length=255)
    patient_identifier: str | None = Field(default=None, max_length=100)
    status: ClaimStatus = ClaimStatus.waiting_for_documents
    assigned_doctor_id: str | None = Field(default=None, max_length=100)
    priority: int = Field(default=3, ge=1, le=5)
    source_channel: str | None = Field(default=None, max_length=100)
    tags: list[str] = Field(default_factory=list)


class ClaimStatusUpdateRequest(BaseModel):
    status: ClaimStatus
    actor_id: str | None = Field(default=None, max_length=100)
    note: str | None = None


class ClaimAssignmentRequest(BaseModel):
    assigned_doctor_id: str = Field(min_length=1, max_length=100)
    actor_id: str | None = Field(default=None, max_length=100)
    status: ClaimStatus | None = None


class ClaimResponse(BaseModel):
    id: UUID
    external_claim_id: str
    patient_name: str | None
    patient_identifier: str | None
    status: ClaimStatus
    assigned_doctor_id: str | None
    priority: int
    source_channel: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class ClaimListResponse(BaseModel):
    total: int
    items: list[ClaimResponse]


class ClaimReportSaveRequest(BaseModel):
    report_html: str = Field(min_length=1)
    report_status: str = Field(default="draft", max_length=30)
    actor_id: str | None = Field(default=None, max_length=100)
    report_source: str = Field(default="doctor", pattern="^(doctor|system)$")


class ClaimReportSaveResponse(BaseModel):
    id: UUID
    claim_id: UUID
    decision_id: UUID | None = None
    version_no: int
    report_status: str
    report_source: str
    created_by: str
    created_at: datetime
    html_size: int



class ClaimReportGrammarCheckRequest(BaseModel):
    report_html: str = Field(min_length=1)
    actor_id: str | None = Field(default=None, max_length=100)


class ClaimReportGrammarCheckResponse(BaseModel):
    corrected_html: str
    changed: bool
    checked_segments: int
    corrected_segments: int
    model: str | None = None
    notes: str | None = None
class ClaimStructuredDataRequest(BaseModel):
    use_llm: bool = False
    force_refresh: bool = True
    actor_id: str | None = Field(default=None, max_length=100)


class ClaimStructuredDataResponse(BaseModel):
    claim_id: UUID
    external_claim_id: str
    company_name: str
    claim_type: str
    insured_name: str
    hospital_name: str
    treating_doctor: str
    treating_doctor_registration_number: str
    doa: str
    dod: str
    diagnosis: str
    complaints: str
    findings: str
    investigation_finding_in_details: str
    medicine_used: str
    high_end_antibiotic_for_rejection: str
    deranged_investigation: str
    claim_amount: str
    conclusion: str
    recommendation: str
    raw_payload: dict = Field(default_factory=dict)
    source: str
    confidence: float | None = None
    created_at: datetime
    updated_at: datetime



class ClaimConclusionGenerateRequest(BaseModel):
    report_html: str = Field(min_length=1)
    actor_id: str | None = Field(default=None, max_length=100)
    rerun_rules: bool = True
    force_source_refresh: bool = False
    use_ai: bool = True


class ClaimConclusionGenerateResponse(BaseModel):
    claim_id: UUID
    conclusion: str
    recommendation: str | None = None
    triggered_rules_count: int = 0
    source: str = "rule_engine"

class ClaimReportAIGenerateRequest(BaseModel):
    actor_id: str | None = Field(default=None, max_length=100)
    report_status: str = Field(default="draft", max_length=30)
    save: bool = True
    auto_generate_structured: bool = True
    use_llm: bool = False
    force_refresh: bool = False


class ClaimReportAIGenerateResponse(BaseModel):
    claim_id: UUID
    report_html: str
    saved: bool = False
    saved_version_no: int | None = None
    model: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ClaimDecideRequest(BaseModel):
    use_llm: bool = False
    force_refresh: bool = False
    auto_advance: bool = False
    auto_generate_report: bool = False
    actor_id: str | None = Field(default=None, max_length=100)


class ClaimPrepareRequest(BaseModel):
    use_llm: bool = False
    force_refresh: bool = False
    actor_id: str | None = Field(default=None, max_length=100)


class ClaimPrepareResponse(BaseModel):
    claim_id: UUID
    queued: bool = True
    lock_acquired: bool | None = None
    extracted_documents: int | None = None
    structured_generated: bool | None = None
    checklist_ran: bool | None = None

class FinalDecisionMLPrediction(BaseModel):
    available: bool = False
    label: str | None = None
    confidence: float = 0.0
    probabilities: dict[str, float] | None = None
    model_version: str | None = None
    training_examples: int = 0
    reason: str | None = None


class ClaimDecideResponse(BaseModel):
    claim_id: UUID
    decision_id: str | None = None
    generated_at: datetime | None = None
    final_status: str  # "approve" | "reject" | "query"
    reason: str
    source: str  # "ai_auto" | "doctor_override" | "hybrid"
    confidence: float
    route_target: str | None = None
    final_status_mapping: str | None = None
    risk_score: float | None = None
    risk_breakdown: list[dict] = Field(default_factory=list)
    conflicts: list[dict] = Field(default_factory=list)
    ml_prediction: FinalDecisionMLPrediction | dict | None = None
    recommendation: str | None = None
    flags: list[dict] = Field(default_factory=list)
    verifications: dict[str, bool | None] = Field(default_factory=dict)


class ClaimAdvanceRequest(BaseModel):
    # workflow status (e.g. auto_approved). Optional if deriving from latest AI decision.
    status: str | None = Field(default=None, max_length=60)
    from_latest_decision: bool = False
    note: str | None = Field(default=None, max_length=2000)
    route_target: str | None = Field(default=None, max_length=120)
    notify_role: str | None = Field(default=None, max_length=40)  # e.g. "auditor"
    auto_notify: bool = False
    actor_id: str | None = Field(default=None, max_length=100)


class ClaimAdvanceResponse(BaseModel):
    claim_id: UUID
    status: ClaimStatus
    workflow_status: str | None = None
    route_target: str | None = None
    notified: bool = False


class ClaimReviewAction(str, Enum):
    approve = "approve"
    reject = "reject"
    query = "query"


class ClaimReviewRequest(BaseModel):
    action: ClaimReviewAction
    note: str | None = Field(default=None, max_length=2000)
    actor_id: str | None = Field(default=None, max_length=100)


class ClaimReviewResponse(BaseModel):
    claim_id: UUID
    action: ClaimReviewAction
    recommendation: str
    claim_status: ClaimStatus
