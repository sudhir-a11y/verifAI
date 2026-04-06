from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.repositories import (
    claim_legacy_data_repo,
    claim_report_uploads_repo,
    claims_repo,
    completed_reports_repo,
)


TAGGING_SUBTAGGING_OPTIONS: dict[str, list[str]] = {
    "Genuine": [
        "Hospitalization verified and found to be genuine",
    ],
    "Fraudulent": [
        "Non cooperation of Hospital / patient during investigation",
        "Circumstantial evidence suggesting of possible fraud",
        "Infalted bills",
        "OPD to IPD conversion",
    ],
}


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


def _normalize_qc_status(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    raw = raw.replace("-", "_").replace(" ", "_")
    if raw in {"yes", "qc_yes", "qcyes", "qc_done", "done"}:
        return "yes"
    if raw in {"no", "qc_no", "qcno"}:
        return "no"
    return ""


def get_completed_reports(
    db: Session,
    *,
    status_filter: str,
    qc_filter: str,
    search_claim: str | None,
    allotment_date: str | None,
    doctor_filter: str | None,
    exclude_tagged: bool,
    sort_order: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    claim_report_uploads_repo.ensure_claim_report_uploads_table(db)
    claim_legacy_data_repo.ensure_claim_legacy_data_table(db)
    claims_repo.ensure_claim_completed_at_column_and_backfill(db)

    normalized_status = status_filter if status_filter in {"pending", "uploaded", "all"} else "pending"
    normalized_qc = "all" if str(qc_filter or "").strip().lower() == "all" else (_normalize_qc_status(qc_filter) or "no")
    normalized_sort = str(sort_order or "updated_desc").strip().lower()
    if normalized_sort not in {"updated_desc", "allotment_asc"}:
        normalized_sort = "updated_desc"

    normalized_allotment = allotment_date if _is_valid_date(allotment_date) else None
    doctors = _split_doctor_filter(doctor_filter)

    total = completed_reports_repo.count_completed_reports(
        db,
        search_claim=search_claim,
        allotment_date=normalized_allotment,
        doctor_tokens=doctors,
        status_filter=normalized_status,
        qc_filter=normalized_qc,
        exclude_tagged=bool(exclude_tagged),
    )

    rows = completed_reports_repo.list_completed_reports(
        db,
        search_claim=search_claim,
        allotment_date=normalized_allotment,
        doctor_tokens=doctors,
        status_filter=normalized_status,
        qc_filter=normalized_qc,
        exclude_tagged=bool(exclude_tagged),
        sort_order=normalized_sort,
        limit=int(limit),
        offset=int(offset),
    )

    items: list[dict[str, Any]] = []
    for row in rows:
        export_uri = str(row.get("export_uri") or "")
        effective_status = str(row.get("effective_report_status") or "pending")
        items.append(
            {
                "claim_uuid": str(row.get("id") or ""),
                "external_claim_id": str(row.get("external_claim_id") or ""),
                "patient_name": str(row.get("patient_name") or ""),
                "assigned_doctor_id": str(row.get("assigned_doctor_id") or ""),
                "report_status": effective_status,
                "effective_report_status": effective_status,
                "report_uploaded": effective_status == "uploaded" or bool(export_uri),
                "export_uri": export_uri,
                "updated_at": row.get("updated_at"),
                "completed_at": row.get("completed_at"),
                "allotment_date": row.get("allotment_date"),
                "report_created_at": row.get("report_created_at"),
                "report_version": int(row.get("report_version") or 0),
                "report_html_available": bool(row.get("report_html_available") or False),
                "latest_report_source": str(row.get("latest_report_source") or "doctor"),
                "doctor_report_html_available": bool(row.get("doctor_report_html_available") or False),
                "system_report_html_available": bool(row.get("system_report_html_available") or False),
                "report_count": int(row.get("report_count") or 0),
                "tagging": _normalize_optional_text(row.get("tagging")),
                "subtagging": _normalize_optional_text(row.get("subtagging")),
                "opinion": _normalize_optional_text(row.get("opinion")),
                "qc_status": str(row.get("qc_status") or "no"),
                "upload_updated_at": row.get("upload_updated_at"),
            }
        )

    return {
        "total": int(total or 0),
        "items": items,
        "tagging_subtagging_options": TAGGING_SUBTAGGING_OPTIONS,
    }


__all__ = ["TAGGING_SUBTAGGING_OPTIONS", "get_completed_reports"]

