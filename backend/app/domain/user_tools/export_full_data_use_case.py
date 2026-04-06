from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.repositories import claim_legacy_data_repo, claim_report_uploads_repo, export_full_data_repo


@dataclass(frozen=True)
class ExportBinaryResult:
    content: bytes
    media_type: str
    filename: str


def _is_valid_date(value: str | None) -> bool:
    if not value:
        return False
    try:
        date.fromisoformat(value)
        return True
    except Exception:
        return False


def export_full_data(
    db: Session,
    *,
    from_date: str | None,
    to_date: str | None,
    allotment_date: str | None,
    output_format: str,
) -> dict[str, Any] | ExportBinaryResult:
    claim_report_uploads_repo.ensure_claim_report_uploads_table(db)
    claim_legacy_data_repo.ensure_claim_legacy_data_table(db)

    def _format_status(raw: str | None) -> str:
        v = str(raw or "").strip().lower()
        if v in {"waiting_for_documents", "ready_for_assignment", "pending"}:
            return "pending"
        return v or "pending"

    def _fmt_date(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, datetime):
            return v.strftime("%d-%m-%Y")
        if isinstance(v, date):
            return v.strftime("%d-%m-%Y")

        s = str(v).strip()
        if not s:
            return ""

        normalized = s.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
            return dt.strftime("%d-%m-%Y")
        except Exception:
            pass

        date_formats = [
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d-%m-%Y %H:%M",
            "%d-%m-%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
        ]
        for fmt in date_formats:
            try:
                dt = datetime.strptime(s, fmt)
                return dt.strftime("%d-%m-%Y")
            except Exception:
                continue

        m = re.search(r"\\b\\d{1,2}[/-]\\d{1,2}[/-]\\d{2,4}\\b", s)
        if m:
            token = m.group(0)
            for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
                try:
                    return datetime.strptime(token, fmt).strftime("%d-%m-%Y")
                except Exception:
                    continue

        m = re.search(r"\\b\\d{4}[/-]\\d{1,2}[/-]\\d{1,2}\\b", s)
        if m:
            token = m.group(0)
            for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
                try:
                    return datetime.strptime(token, fmt).strftime("%d-%m-%Y")
                except Exception:
                    continue

        return s

    def _fmt_datetime(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, datetime):
            return v.strftime("%d-%m-%Y %H:%M:%S")
        if isinstance(v, date):
            return datetime(v.year, v.month, v.day).strftime("%d-%m-%Y %H:%M:%S")

        s = str(v).strip()
        if not s:
            return ""

        normalized = s.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
            return dt.strftime("%d-%m-%Y %H:%M:%S")
        except Exception:
            pass

        datetime_formats = [
            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%Y-%m-%d",
            "%Y/%m/%d",
        ]
        for fmt in datetime_formats:
            try:
                dt = datetime.strptime(s, fmt)
                return dt.strftime("%d-%m-%Y %H:%M:%S")
            except Exception:
                continue

        return s

    def _tag_at(tags: Any, idx: int) -> str:
        if isinstance(tags, list):
            if 0 <= idx < len(tags):
                return str(tags[idx] or "").strip()
            return ""
        return ""

    def _legacy_get(payload_obj: Any, *keys: str) -> str:
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

    safe_from = from_date if _is_valid_date(from_date) else None
    safe_to = to_date if _is_valid_date(to_date) else None
    safe_allotment = allotment_date if _is_valid_date(allotment_date) else None

    rows = export_full_data_repo.list_export_full_data_rows(
        db,
        from_date=safe_from,
        to_date=safe_to,
        allotment_date=safe_allotment,
    )

    items = [
        {
            "external_claim_id": str(r.get("external_claim_id") or ""),
            "patient_name": str(r.get("patient_name") or ""),
            "patient_identifier": str(r.get("patient_identifier") or ""),
            "status": _format_status(r.get("status")),
            "assigned_doctor_id": str(r.get("assigned_doctor_id") or ""),
            "priority": int(r.get("priority") or 0),
            "source_channel": str(r.get("source_channel") or ""),
            "created_at": str(r.get("created_at") or ""),
            "updated_at": str(r.get("updated_at") or ""),
            "allotment_date": str(r.get("allotment_date") or ""),
            "report_status": str(r.get("report_status") or ""),
            "export_uri": str(r.get("export_uri") or ""),
            "report_version": int(r.get("version_no") or 0),
            "report_created_at": str(r.get("report_created_at") or ""),
        }
        for r in rows
    ]

    legacy_fieldnames = [
        "claim_date",
        "claim_id",
        "claim_type",
        "policy_number",
        "policy_type",
        "policy_start_date",
        "policy_end_date",
        "benef_name",
        "benef_age",
        "benef_gender",
        "pri_benef_name",
        "benef_sum_insured",
        "relation_type",
        "hospital_name",
        "hospital_pincode",
        "hospital_city",
        "hospital_state",
        "claim_amount",
        "doa_date",
        "dod_date",
        "claimant_ir",
        "hospital_is_network",
        "trigger_remarks",
        "document_required",
        "primary_icd_group",
        "primary_ailment_code",
        "treatment_type",
        "bill_deduction_reason",
        "vendor_name",
        "allocation_date",
        "document_status",
        "final_status",
        "report_export_status",
        "tagging",
        "subtagging",
        "opinion",
        "qc_status",
        "created_at",
        "updated_at",
    ]

    def _claim_id_number(value: Any) -> int | str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        digits = re.sub(r"[^0-9]", "", raw)
        if not digits:
            return raw
        try:
            return int(digits)
        except Exception:
            return raw

    legacy_items: list[dict[str, Any]] = []
    for r in rows:
        tags = r.get("tags")
        status_value = _format_status(r.get("status"))
        payload_obj = r.get("legacy_payload")
        if isinstance(payload_obj, str):
            try:
                payload_obj = json.loads(payload_obj)
            except Exception:
                payload_obj = {}
        if not isinstance(payload_obj, dict):
            payload_obj = {}

        legacy_items.append(
            {
                "claim_date": _fmt_date(_legacy_get(payload_obj, "claim_date") or r.get("created_at")),
                "claim_id": _claim_id_number(
                    _legacy_get(payload_obj, "claim_id") or str(r.get("external_claim_id") or "")
                ),
                "claim_type": _legacy_get(payload_obj, "claim_type") or _tag_at(tags, 0),
                "policy_number": _legacy_get(payload_obj, "policy_number") or str(r.get("patient_identifier") or ""),
                "policy_type": _legacy_get(payload_obj, "policy_type") or _tag_at(tags, 1),
                "policy_start_date": _fmt_date(_legacy_get(payload_obj, "policy_start_date")),
                "policy_end_date": _fmt_date(_legacy_get(payload_obj, "policy_end_date")),
                "benef_name": _legacy_get(payload_obj, "benef_name") or str(r.get("patient_name") or ""),
                "benef_age": _legacy_get(payload_obj, "benef_age"),
                "benef_gender": _legacy_get(payload_obj, "benef_gender"),
                "pri_benef_name": _legacy_get(payload_obj, "pri_benef_name"),
                "benef_sum_insured": _legacy_get(payload_obj, "benef_sum_insured"),
                "relation_type": _legacy_get(payload_obj, "relation_type"),
                "hospital_name": _legacy_get(payload_obj, "hospital_name") or _tag_at(tags, 3),
                "hospital_pincode": _legacy_get(payload_obj, "hospital_pincode"),
                "hospital_city": _legacy_get(payload_obj, "hospital_city"),
                "hospital_state": _legacy_get(payload_obj, "hospital_state"),
                "claim_amount": _legacy_get(payload_obj, "claim_amount"),
                "doa_date": _fmt_date(
                    _legacy_get(
                        payload_obj,
                        "doa_date",
                        "doa",
                        "doa date",
                        "date_of_admission",
                        "date of admission",
                        "admission_date",
                        "admission date",
                    )
                ),
                "dod_date": _fmt_date(
                    _legacy_get(
                        payload_obj,
                        "dod_date",
                        "dod",
                        "dod date",
                        "date_of_discharge",
                        "date of discharge",
                        "discharge_date",
                        "discharge date",
                    )
                ),
                "claimant_ir": _legacy_get(payload_obj, "claimant_ir"),
                "hospital_is_network": _legacy_get(payload_obj, "hospital_is_network"),
                "trigger_remarks": _legacy_get(payload_obj, "trigger_remarks") or str(r.get("trigger_remarks") or ""),
                "document_required": _legacy_get(payload_obj, "document_required"),
                "primary_icd_group": _legacy_get(payload_obj, "primary_icd_group") or _tag_at(tags, 2),
                "primary_ailment_code": _legacy_get(payload_obj, "primary_ailment_code"),
                "treatment_type": _legacy_get(payload_obj, "treatment_type") or _tag_at(tags, 4),
                "bill_deduction_reason": _legacy_get(payload_obj, "bill_deduction_reason"),
                "vendor_name": _legacy_get(payload_obj, "vendor_name") or str(r.get("source_channel") or ""),
                "allocation_date": _fmt_date(_legacy_get(payload_obj, "allocation_date") or r.get("allotment_date")),
                "document_status": _legacy_get(payload_obj, "document_status")
                or ("uploaded" if int(r.get("documents") or 0) > 0 else "pending"),
                "final_status": _legacy_get(payload_obj, "final_status") or status_value,
                "report_export_status": _legacy_get(payload_obj, "report_export_status")
                or str(r.get("report_export_status") or "pending"),
                "tagging": _legacy_get(payload_obj, "tagging") or str(r.get("tagging") or ""),
                "subtagging": _legacy_get(payload_obj, "subtagging") or str(r.get("subtagging") or ""),
                "opinion": _legacy_get(payload_obj, "opinion") or str(r.get("opinion") or ""),
                "qc_status": _legacy_get(payload_obj, "qc_status") or str(r.get("qc_status") or "no"),
                "created_at": _fmt_datetime(_legacy_get(payload_obj, "created_at") or r.get("created_at")),
                "updated_at": _fmt_datetime(_legacy_get(payload_obj, "updated_at") or r.get("updated_at")),
            }
        )

    normalized_format = str(output_format or "json").strip().lower()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if normalized_format == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=legacy_fieldnames, extrasaction="ignore")
        writer.writeheader()
        for item in legacy_items:
            writer.writerow(item)
        return ExportBinaryResult(
            content=buf.getvalue().encode("utf-8"),
            media_type="text/csv",
            filename=f"user_full_data_{stamp}.csv",
        )

    if normalized_format in {"excel", "xlsx"}:
        try:
            from openpyxl import Workbook
            from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

            def _xlsx_value(v: Any) -> Any:
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    return v
                raw = "" if v is None else str(v)
                cleaned = ILLEGAL_CHARACTERS_RE.sub("", raw)
                if len(cleaned) > 32767:
                    cleaned = cleaned[:32767]
                return cleaned

            wb = Workbook()
            ws = wb.active
            ws.title = "user_full_data"
            ws.append(legacy_fieldnames)
            for item in legacy_items:
                ws.append([_xlsx_value(item.get(col, "")) for col in legacy_fieldnames])

            out = io.BytesIO()
            wb.save(out)
            return ExportBinaryResult(
                content=out.getvalue(),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename=f"user_full_data_{stamp}.xlsx",
            )
        except Exception:
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=legacy_fieldnames, extrasaction="ignore")
            writer.writeheader()
            for item in legacy_items:
                writer.writerow(item)
            return ExportBinaryResult(
                content=buf.getvalue().encode("utf-8"),
                media_type="text/csv",
                filename=f"user_full_data_{stamp}.csv",
            )

    return {"total": len(items), "items": items}

