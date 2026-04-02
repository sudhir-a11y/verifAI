from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.extraction import ExtractionProvider


class PolicyIngestRequest(BaseModel):
    policy_code: str = Field(min_length=1, max_length=120)
    policy_name: str | None = Field(default=None, max_length=255)
    policy_text: str = Field(min_length=20)
    source_uri: str | None = Field(default=None, max_length=1000)
    metadata: dict = Field(default_factory=dict)
    chunk_size_chars: int = Field(default=1400, ge=400, le=8000)
    chunk_overlap_chars: int = Field(default=160, ge=0, le=1200)
    embed_chunks: bool = True
    actor_id: str | None = Field(default=None, max_length=100)


class PolicyIngestResponse(BaseModel):
    policy_document_id: UUID
    policy_code: str
    policy_name: str | None = None
    chunks_created: int
    embedded_chunks: int
    created_at: datetime


class PolicyChunkHit(BaseModel):
    chunk_id: UUID
    chunk_index: int
    score: float
    lexical_score: float
    vector_score: float | None = None
    text: str


class PolicyRagValidateRequest(BaseModel):
    policy_code: str = Field(min_length=1, max_length=120)
    top_k: int = Field(default=8, ge=1, le=25)
    extraction_provider: ExtractionProvider = ExtractionProvider.aws_textract
    run_extraction_if_missing: bool = True
    use_llm_reasoning: bool = True
    actor_id: str | None = Field(default=None, max_length=100)


class PolicyRagValidateResponse(BaseModel):
    validation_id: UUID
    claim_id: UUID
    external_claim_id: str
    policy_code: str
    structured_claim: dict
    retrieved_policy_chunks: list[PolicyChunkHit]
    rag_evaluation: dict
    created_at: datetime
