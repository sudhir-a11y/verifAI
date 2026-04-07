from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from fastapi import HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps.auth import require_roles
from app.ai.document_analyzer import DEFAULT_QUERIES, analyze_hits, analyze_pages
from app.ai.document_indexer import Chunk, DocumentIndex, build_index
from app.core.config import settings
from app.db.session import get_db
from app.domain.auth.service import AuthenticatedUser
from app.repositories import document_analyses_repo, document_indexes_repo
from app.schemas.auth import UserRole
from app.schemas.document_analyzer import (
    AnalyzeIndexRequest,
    AnalyzeIndexResponse,
    CreateIndexRequest,
    CreateIndexResponse,
    DocumentAnalyzeRequest,
    OCRPage,
    SearchIndexResponse,
)

router = APIRouter(prefix="/document-analyzer", tags=["document-analyzer"])


@router.post("/analyze")
def analyze_ocr_pages_endpoint(
    payload: DocumentAnalyzeRequest,
    _current_user: AuthenticatedUser = Depends(
        require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)
    ),
) -> dict[str, Any]:
    return analyze_pages(
        [p.model_dump() for p in payload.pages],
        queries=payload.queries,
        top_k_per_query=payload.top_k_per_query,
        embedding_provider=payload.embedding_provider,
        use_ai=bool(payload.use_ai),
    )


@router.post("/index", response_model=CreateIndexResponse)
def create_index_endpoint(
    payload: CreateIndexRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(
        require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)
    ),
) -> CreateIndexResponse:
    idx = build_index([p.model_dump() for p in payload.pages], provider=payload.embedding_provider)
    index_id = uuid4()
    chunks = [c.__dict__ for c in idx.chunks]
    embeddings = idx.embeddings
    dim = len(embeddings[0]) if embeddings else 0

    meta = document_indexes_repo.insert_index(
        db,
        index_id=index_id,
        embedding_provider=payload.embedding_provider,
        embedding_dim=dim,
        chunks=chunks,
        embeddings=embeddings,
        created_by=current_user.username,
    )
    db.commit()
    return CreateIndexResponse(
        index_id=index_id,
        embedding_provider=str(meta.get("embedding_provider") or payload.embedding_provider),
        embedding_dim=int(meta.get("embedding_dim") or dim),
        chunk_count=len(chunks),
        created_by=meta.get("created_by"),
        created_at=meta.get("created_at"),
    )


@router.get("/index/{index_id}/search", response_model=SearchIndexResponse)
def search_index_endpoint(
    index_id: UUID,
    q: str = Query(min_length=1),
    top_k: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
    _current_user: AuthenticatedUser = Depends(
        require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)
    ),
) -> SearchIndexResponse:
    row = document_indexes_repo.get_index(db, index_id=index_id)
    if row is None:
        raise HTTPException(status_code=404, detail="index not found")

    idx = DocumentIndex(
        chunks=[
            # stored chunk dicts
            Chunk(
                chunk_id=str(c.get("chunk_id") or ""),
                page=int(c.get("page") or 0),
                text=str(c.get("text") or ""),
            )
            for c in (row.get("chunks") or [])
            if isinstance(c, dict)
        ],
        embeddings=[[float(x) for x in v] for v in (row.get("embeddings") or []) if isinstance(v, list)],
        embedding_provider=str(row.get("embedding_provider") or "auto"),
    )
    hits = [h.__dict__ for h in idx.search(q, top_k=top_k)]
    return SearchIndexResponse(index_id=index_id, query=q, top_k=top_k, hits=hits)


@router.post("/index/{index_id}/analyze", response_model=AnalyzeIndexResponse)
def analyze_index_endpoint(
    index_id: UUID,
    payload: AnalyzeIndexRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(
        require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)
    ),
) -> AnalyzeIndexResponse:
    row = document_indexes_repo.get_index(db, index_id=index_id)
    if row is None:
        raise HTTPException(status_code=404, detail="index not found")

    chunks = [c for c in (row.get("chunks") or []) if isinstance(c, dict)]
    embeddings = [v for v in (row.get("embeddings") or []) if isinstance(v, list)]
    idx = DocumentIndex(
        chunks=[
            Chunk(
                chunk_id=str(c.get("chunk_id") or ""),
                page=int(c.get("page") or 0),
                text=str(c.get("text") or ""),
            )
            for c in chunks
        ],
        embeddings=[[float(x) for x in v] for v in embeddings],
        embedding_provider=str(row.get("embedding_provider") or "auto"),
    )

    query_list = [str(q).strip() for q in (payload.queries or DEFAULT_QUERIES) if str(q).strip()]
    hits_by_query = {q: [h.__dict__ for h in idx.search(q, top_k=payload.top_k_per_query)] for q in query_list}

    analysis = analyze_hits(hits_by_query, queries=query_list, use_ai=bool(payload.use_ai))
    model_name = None
    if bool(payload.use_ai) and bool(settings.openai_api_key):
        model_name = str(settings.openai_rag_model or settings.openai_model or "").strip() or None

    inserted = document_analyses_repo.insert_analysis(
        db,
        index_id=index_id,
        queries=query_list,
        top_k_per_query=payload.top_k_per_query,
        use_ai=bool(payload.use_ai),
        model_name=model_name,
        analysis=analysis if isinstance(analysis, dict) else {},
        created_by=current_user.username,
    )
    db.commit()
    return AnalyzeIndexResponse(
        analysis_id=int(inserted.get("id") or 0),
        index_id=index_id,
        analysis=inserted.get("analysis") or {},
        created_by=inserted.get("created_by"),
        created_at=inserted.get("created_at"),
    )
