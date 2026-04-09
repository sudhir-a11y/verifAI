import signal

import pytest


def test_load_high_end_medicine_catalog_does_not_hang(monkeypatch) -> None:
    if not hasattr(signal, "SIGALRM"):
        pytest.skip("SIGALRM not available on this platform")

    from app.ai.structuring import service as structuring_service
    from app.repositories import medicine_catalog_repo

    monkeypatch.setattr(
        medicine_catalog_repo,
        "load_high_end_antibiotic_catalog",
        lambda _db, _names: [
            {
                "medicine_name": "Meropenem 1g",
                "components": "meropenem",
                "is_high_end_antibiotic": True,
            }
        ],
    )

    class TimeoutError(Exception):
        pass

    def _handler(_signum, _frame):
        raise TimeoutError("catalog load hung")

    prev_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _handler)
    signal.alarm(2)
    try:
        out = structuring_service._load_high_end_medicine_catalog(db=None)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, prev_handler)

    assert isinstance(out, list)
    # One base row + one enriched alias row.
    assert len(out) == 2
    assert any(isinstance(row, dict) and row.get("aliases") for row in out)

