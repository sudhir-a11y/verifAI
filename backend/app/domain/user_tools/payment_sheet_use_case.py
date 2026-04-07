from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.repositories import claims_repo
from app.repositories.payment_sheet_repo import ensure_user_bank_details_table, list_payment_sheet_rows


@dataclass(frozen=True)
class InvalidMonthError(Exception):
    message: str


def _parse_payment_rate(value: Any) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    cleaned = re.sub(r"[^0-9.\\-]", "", raw)
    if cleaned in {"", "-", ".", "-."}:
        return 0.0
    try:
        parsed = float(cleaned)
    except Exception:
        return 0.0
    return parsed if parsed >= 0 else 0.0


def _next_month_start(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


def _resolve_month_start(month: str | None) -> date:
    month_text = str(month or "").strip()
    if month_text:
        # Expect HTML `<input type="month">` style value, e.g. "2026-03".
        if not re.fullmatch(r"\d{4}-\d{2}", month_text):
            raise InvalidMonthError("month must be in YYYY-MM format.")
        try:
            return date.fromisoformat(f"{month_text}-01")
        except Exception as exc:
            raise InvalidMonthError("Invalid month value.") from exc

    ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    this_month_start = date(ist_now.year, ist_now.month, 1)
    return (this_month_start - timedelta(days=1)).replace(day=1)


def get_payment_sheet(
    db: Session,
    *,
    month: str | None,
    include_zero_cases: bool,
) -> dict[str, Any]:
    ensure_user_bank_details_table(db)
    claims_repo.ensure_claim_completed_at_column_and_backfill(db)

    month_start = _resolve_month_start(month)
    month_end = _next_month_start(month_start)

    rows = list_payment_sheet_rows(db, month_start=month_start, month_end=month_end)

    items: list[dict[str, Any]] = []
    total_cases = 0
    total_amount = 0.0
    for row in rows:
        completed_cases = int(row.get("completed_cases") or 0)
        if not include_zero_cases and completed_cases <= 0:
            continue
        rate_raw = str(row.get("payment_rate_raw") or "").strip()
        rate_numeric = _parse_payment_rate(rate_raw)
        amount_total = float(rate_numeric * completed_cases)
        total_cases += completed_cases
        total_amount += amount_total
        items.append(
            {
                "user_id": int(row.get("user_id") or 0),
                "username": str(row.get("username") or ""),
                "role": str(row.get("role") or ""),
                "rate_raw": rate_raw,
                "rate_numeric": rate_numeric,
                "completed_cases": completed_cases,
                "amount_total": amount_total,
                "bank_is_active": bool(row.get("bank_is_active")),
            }
        )

    return {
        "month": month_start.strftime("%Y-%m"),
        "month_label": month_start.strftime("%b %Y"),
        "include_zero_cases": bool(include_zero_cases),
        "total_users": len(items),
        "total_cases": int(total_cases),
        "total_amount": float(total_amount),
        "items": items,
    }
