from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.domain.admin_tools.analysis_import_service import import_analysis_results_from_rows
from app.infrastructure.parsers.sql_dump_parser import iter_table_rows_from_sql_dump_bytes


@dataclass(frozen=True)
class InvalidSqlDumpError(Exception):
    message: str


def import_analysis_sql_dump(
    db: Session,
    *,
    filename: str,
    payload: bytes,
    limit: int,
    imported_by_username: str,
) -> dict[str, Any]:
    name = str(filename or "").strip()
    if not name.lower().endswith(".sql"):
        raise InvalidSqlDumpError("Please upload a .sql dump file")
    if not payload:
        raise InvalidSqlDumpError("empty file")

    rows_iter: Iterable[dict[str, Any]] = iter_table_rows_from_sql_dump_bytes(payload, "openai_analysis_results")
    summary = import_analysis_results_from_rows(
        db,
        rows_iter,
        limit=int(limit or 0),
        created_by_system=f"system:legacy_sql_import:{imported_by_username}",
    )
    return {"ok": True, "file": name, "limit": int(limit or 0), "imported_by": imported_by_username, **summary}
