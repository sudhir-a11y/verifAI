from __future__ import annotations

import json
from threading import Lock
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import engine

_READY = False
_LOCK = Lock()


def ensure_document_indexes_table() -> None:
    """Create table once per process (avoid DDL inside request sessions)."""
    global _READY
    if _READY:
        return
    with _LOCK:
        if _READY:
            return
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS document_indexes (
                        id UUID PRIMARY KEY,
                        embedding_provider VARCHAR(30) NOT NULL DEFAULT 'auto',
                        embedding_dim INT NOT NULL DEFAULT 0,
                        chunks JSONB NOT NULL DEFAULT '[]'::jsonb,
                        embeddings JSONB NOT NULL DEFAULT '[]'::jsonb,
                        created_by VARCHAR(100),
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_document_indexes_created_at
                    ON document_indexes (created_at DESC)
                    """
                )
            )
        _READY = True


def insert_index(
    db: Session,
    *,
    index_id: UUID,
    embedding_provider: str,
    embedding_dim: int,
    chunks: list[dict[str, Any]],
    embeddings: list[list[float]],
    created_by: str | None,
) -> dict[str, Any]:
    ensure_document_indexes_table()
    row = db.execute(
        text(
            """
            INSERT INTO document_indexes (
                id,
                embedding_provider,
                embedding_dim,
                chunks,
                embeddings,
                created_by
            )
            VALUES (
                :id,
                :embedding_provider,
                :embedding_dim,
                CAST(:chunks AS jsonb),
                CAST(:embeddings AS jsonb),
                :created_by
            )
            RETURNING
                id,
                embedding_provider,
                embedding_dim,
                created_by,
                created_at
            """
        ),
        {
            "id": str(index_id),
            "embedding_provider": str(embedding_provider or "auto")[:30],
            "embedding_dim": int(embedding_dim or 0),
            "chunks": json.dumps(chunks or [], ensure_ascii=False, allow_nan=False),
            "embeddings": json.dumps(embeddings or [], ensure_ascii=False, allow_nan=False),
            "created_by": (str(created_by).strip()[:100] if created_by else None),
        },
    ).mappings().one()
    return dict(row)


def get_index(db: Session, *, index_id: UUID) -> dict[str, Any] | None:
    ensure_document_indexes_table()
    row = db.execute(
        text(
            """
            SELECT
                id,
                embedding_provider,
                embedding_dim,
                chunks,
                embeddings,
                created_by,
                created_at
            FROM document_indexes
            WHERE id = :id
            LIMIT 1
            """
        ),
        {"id": str(index_id)},
    ).mappings().first()
    return dict(row) if row is not None else None

