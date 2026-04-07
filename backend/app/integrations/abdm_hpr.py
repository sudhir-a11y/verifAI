"""ABDM HPR integration facade (prompt-compatible import path).

The actual client implementation lives in `app.infrastructure.integrations.abdm_hpr`.
This module exists to match older docs/prompts that reference
`backend/app/integrations/abdm_hpr.py`.
"""

from __future__ import annotations

from typing import Any

from app.infrastructure.integrations.abdm_hpr import (
    fetch_doctor_by_hpr_id as fetch_doctor_details,
    verify_doctor,
)


__all__ = ["fetch_doctor_details", "verify_doctor"]

