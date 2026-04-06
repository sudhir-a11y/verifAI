from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.repositories import claims_repo, doctor_completion_stats_repo
from app.schemas.auth import UserRole


class InvalidMonthError(ValueError):
    pass


def _normalize_optional_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_doctor_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def get_doctor_completion_stats(
    db: Session,
    *,
    month: str | None,
    doctor_username: str | None,
    current_user_role: UserRole,
    current_username: str,
) -> dict[str, Any]:
    claims_repo.ensure_claim_completed_at_column_and_backfill(db)

    month_text = str(month or "").strip()
    selected_month_start: date | None = None
    if month_text:
        if not re.fullmatch(r"\d{4}-\d{2}", month_text):
            raise InvalidMonthError("month must be in YYYY-MM format.")
        try:
            selected_month_start = date.fromisoformat(f"{month_text}-01")
        except ValueError as exc:
            raise InvalidMonthError("Invalid month value.") from exc

    if current_user_role == UserRole.doctor:
        scoped_doctor_key = _normalize_doctor_key(current_username)
        scoped_doctor_label = str(current_username or "").strip()
    else:
        requested_doctor = _normalize_optional_text(doctor_username)
        scoped_doctor_key = _normalize_doctor_key(requested_doctor)
        scoped_doctor_label = requested_doctor

    month_rows = doctor_completion_stats_repo.list_month_wise_closed(db, doctor_key=scoped_doctor_key)

    if selected_month_start is None and month_rows:
        top_row = month_rows[0]
        top_month = top_row.get("month_start")
        if isinstance(top_month, date):
            selected_month_start = top_month
        else:
            top_key = str(top_row.get("month_key") or "").strip()
            if re.fullmatch(r"\d{4}-\d{2}", top_key):
                selected_month_start = date.fromisoformat(f"{top_key}-01")

    day_rows: list[dict[str, Any]] = []
    if selected_month_start is not None:
        day_rows = doctor_completion_stats_repo.list_day_wise_closed(
            db,
            doctor_key=scoped_doctor_key,
            month_start=selected_month_start,
        )

    selected_month_value = selected_month_start.strftime("%Y-%m") if selected_month_start else ""
    return {
        "doctor_scope": scoped_doctor_label or "all",
        "selected_month": selected_month_value,
        "month_wise_closed": [
            {
                "month": str(r.get("month_key") or ""),
                "label": str(r.get("month_label") or r.get("month_key") or ""),
                "closed": int(r.get("closed_count") or 0),
            }
            for r in month_rows
        ],
        "day_wise_closed": [
            {
                "date": str(r.get("completed_date") or ""),
                "closed": int(r.get("closed_count") or 0),
            }
            for r in day_rows
        ],
    }


__all__ = ["InvalidMonthError", "get_doctor_completion_stats"]

