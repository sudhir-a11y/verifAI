from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.repositories import (
    claim_document_status_repo,
    claim_legacy_data_repo,
    claim_report_uploads_repo,
)
from app.schemas.auth import UserRole


_EMPTY_LIKE_TEXT_VALUES = {
    "na",
    "n/a",
    "not available",
    "none",
    "nil",
    "null",
    "-",
    ".",
}


def _normalize_optional_text(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.lower() in _EMPTY_LIKE_TEXT_VALUES:
        return ""
    return raw


def _is_valid_date(value: str | None) -> bool:
    if not value:
        return False
    try:
        date.fromisoformat(value)
        return True
    except Exception:
        return False


def _normalize_doctor_token(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _split_doctor_filter(raw: str | None) -> list[str]:
    tokens: list[str] = []
    for part in str(raw or "").split(","):
        normalized = _normalize_doctor_token(part)
        if normalized:
            tokens.append(normalized)
    return tokens


def get_claim_document_status(
    db: Session,
    *,
    search_claim: str | None,
    allotment_date: str | None,
    status_filter: str,
    doctor_filter: str | None,
    document_upload: str,
    exclude_tagged: bool,
    exclude_completed: bool,
    exclude_completed_uploaded: bool,
    exclude_withdrawn: bool,
    sort_order: str,
    limit: int,
    offset: int,
    current_user_role: UserRole,
    current_username: str,
) -> dict[str, Any]:
    claim_legacy_data_repo.ensure_claim_legacy_data_table(db)
    claim_report_uploads_repo.ensure_claim_report_uploads_table(db)

    valid_statuses = {
        "ready_for_assignment",
        "waiting_for_documents",
        "pending",
        "in_review",
        "needs_qc",
        "completed",
        "withdrawn",
        "all",
    }
    normalized_status = (status_filter or "all").strip().lower()
    if normalized_status not in valid_statuses:
        normalized_status = "all"

    normalized_document_upload = (document_upload or "all").strip().lower()
    if normalized_document_upload not in {"all", "yes", "no"}:
        normalized_document_upload = "all"

    order_sql = "ASC" if (sort_order or "").strip().lower() == "asc" else "DESC"

    filters: list[str] = []
    params: dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
    completed_uploaded_expr = (
        "((NULLIF(TRIM(COALESCE(um.tagging, '')), '') IS NOT NULL "
        "OR NULLIF(TRIM(COALESCE(um.subtagging, '')), '') IS NOT NULL "
        "OR NULLIF(TRIM(COALESCE(um.opinion, '')), '') IS NOT NULL) "
        "OR COALESCE(um.report_export_status, 'pending') = 'uploaded' "
        "OR COALESCE(rv.export_uri, '') <> '')"
    )

    if search_claim and str(search_claim).strip():
        filters.append("LOWER(c.external_claim_id) LIKE :search_claim")
        params["search_claim"] = f"%{str(search_claim).strip().lower()}%"

    if _is_valid_date(allotment_date):
        filters.append(
            """
            COALESCE(
                la.allotment_date,
                CASE
                    WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{4}-\\d{2}-\\d{2}$'
                        THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD')
                    WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}-\\d{2}-\\d{4}$'
                        THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD-MM-YYYY')
                    WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}/\\d{2}/\\d{4}$'
                        THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD/MM/YYYY')
                    ELSE NULL
                END
            ) = :allotment_date
            """
        )
        params["allotment_date"] = allotment_date

    if normalized_document_upload == "yes":
        filters.append("COALESCE(ds.documents, 0) > 0")
    elif normalized_document_upload == "no":
        filters.append("COALESCE(ds.documents, 0) = 0")

    if normalized_status == "pending":
        filters.append("c.status = 'waiting_for_documents'")
        filters.append("COALESCE(ds.documents, 0) > 0")
    elif normalized_status == "waiting_for_documents":
        filters.append("c.status = 'waiting_for_documents'")
        filters.append("COALESCE(ds.documents, 0) = 0")
    elif normalized_status != "all":
        filters.append("c.status = :status_filter")
        params["status_filter"] = normalized_status

    if exclude_completed:
        filters.append("c.status <> 'completed'")
    if exclude_completed_uploaded:
        filters.append(f"NOT (c.status = 'completed' AND {completed_uploaded_expr})")
    auto_exclude_withdrawn = normalized_status != "withdrawn"
    if exclude_withdrawn or auto_exclude_withdrawn:
        filters.append("c.status <> 'withdrawn'")
    if exclude_tagged and current_user_role != UserRole.doctor:
        filters.append("NULLIF(TRIM(COALESCE(um.tagging, '')), '') IS NULL")

    effective_doctors = _split_doctor_filter(doctor_filter)
    if current_user_role == UserRole.doctor:
        doctor_token = _normalize_doctor_token(current_username)
        effective_doctors = [doctor_token] if doctor_token else []

    if effective_doctors:
        doctor_clauses: list[str] = []
        for idx, doctor in enumerate(effective_doctors):
            key = f"doctor_{idx}"
            params[key] = doctor
            doctor_clauses.append(
                f":{key} = ANY(string_to_array(regexp_replace(LOWER(COALESCE(c.assigned_doctor_id, '')), '[^a-z0-9,]+', '', 'g'), ','))"
            )
        filters.append("(" + " OR ".join(doctor_clauses) + ")")

    where_sql = ("WHERE " + " AND ".join(filters)) if filters else ""

    total = claim_document_status_repo.count_claim_document_status(db, where_sql=where_sql, params=params)
    rows = claim_document_status_repo.list_claim_document_status_rows(
        db,
        where_sql=where_sql,
        order_sql=order_sql,
        params=params,
    )

    def _legacy_text(payload_obj: Any, *keys: str) -> str:
        if not isinstance(payload_obj, dict):
            return ""
        for key in keys:
            value = payload_obj.get(key)
            if value is None:
                continue
            text_value = str(value).strip()
            if text_value:
                return text_value
        return ""

    def _tag_at(tags_value: Any, idx: int) -> str:
        if isinstance(tags_value, list) and 0 <= idx < len(tags_value):
            return str(tags_value[idx] or "").strip()
        if isinstance(tags_value, str):
            try:
                parsed = json.loads(tags_value)
            except Exception:
                parsed = None
            if isinstance(parsed, list) and 0 <= idx < len(parsed):
                return str(parsed[idx] or "").strip()
        return ""

    items: list[dict[str, Any]] = []
    for r in rows:
        legacy_payload = r.get("legacy_payload") if isinstance(r.get("legacy_payload"), dict) else {}
        tags_value = r.get("tags")
        claim_type = _legacy_text(legacy_payload, "claim_type", "claim type", "case_type", "case type") or _tag_at(
            tags_value, 0
        )
        treatment_type = _legacy_text(legacy_payload, "treatment_type", "treatment type", "treatment-type") or _tag_at(
            tags_value, 4
        )
        items.append(
            {
                "id": str(r.get("id") or ""),
                "external_claim_id": str(r.get("external_claim_id") or ""),
                "assigned_doctor_id": str(r.get("assigned_doctor_id") or ""),
                "status": str(r.get("status") or ""),
                "status_display": str(r.get("status_display") or ""),
                "assigned_at": str(r.get("assigned_at") or ""),
                "allotment_date": str(r.get("allotment_date") or ""),
                "documents": int(r.get("documents") or 0),
                "source_files": int(r.get("source_files") or 0),
                "last_upload": str(r.get("last_upload") or ""),
                "last_uploaded_by": str(r.get("last_uploaded_by") or ""),
                "final_status": str(r.get("final_status") or "Pending"),
                "doa_date": str(r.get("doa_date") or ""),
                "dod_date": str(r.get("dod_date") or ""),
                "opinion": str(r.get("opinion") or ""),
                "auditor_learning": str(r.get("auditor_learning") or ""),
                "auditor_comment": str(r.get("auditor_comment") or ""),
                "auditor_comment_by": str(r.get("auditor_comment_by") or ""),
                "auditor_comment_at": str(r.get("auditor_comment_at") or ""),
                "claim_type": claim_type,
                "treatment_type": treatment_type,
                "legacy_payload": legacy_payload,
            }
        )

    return {"total": int(total or 0), "items": items}


__all__ = ["get_claim_document_status"]

