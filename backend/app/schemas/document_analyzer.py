from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class OCRPage(BaseModel):
    page: int = Field(ge=1)
    text: str = Field(default="", max_length=400_000)


class CreateIndexRequest(BaseModel):
    pages: list[OCRPage] = Field(default_factory=list)
    embedding_provider: str = Field(default="auto", max_length=30)

class DocumentAnalyzeRequest(BaseModel):
    pages: list[OCRPage] = Field(default_factory=list)
    queries: list[str] | None = None
    top_k_per_query: int = Field(default=5, ge=1, le=20)
    embedding_provider: str = Field(default="auto", max_length=30)
    use_ai: bool = True


class CreateIndexResponse(BaseModel):
    index_id: UUID
    embedding_provider: str
    embedding_dim: int
    chunk_count: int
    created_by: str | None = None
    created_at: datetime


class SearchIndexResponse(BaseModel):
    index_id: UUID
    query: str
    top_k: int
    hits: list[dict] = Field(default_factory=list)


class AnalyzeIndexRequest(BaseModel):
    queries: list[str] | None = None
    top_k_per_query: int = Field(default=5, ge=1, le=20)
    use_ai: bool = True


class AnalyzeIndexResponse(BaseModel):
    analysis_id: int
    index_id: UUID
    analysis: dict = Field(default_factory=dict)
    created_by: str | None = None
    created_at: datetime
