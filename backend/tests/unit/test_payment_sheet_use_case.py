from datetime import date

import pytest

from app.domain.user_tools import payment_sheet_use_case


def test_resolve_month_start_accepts_yyyy_mm() -> None:
    assert payment_sheet_use_case._resolve_month_start("2026-03") == date(2026, 3, 1)


@pytest.mark.parametrize("value", ["2026-3", "03-2026", "2026/03", "2026-13", "abcd-ef"])
def test_resolve_month_start_rejects_invalid_format(value: str) -> None:
    with pytest.raises(payment_sheet_use_case.InvalidMonthError):
        payment_sheet_use_case._resolve_month_start(value)

