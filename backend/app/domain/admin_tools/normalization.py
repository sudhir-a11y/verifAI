from __future__ import annotations

import json
import re
from typing import Any


def normalize_json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except json.JSONDecodeError:
            return [value]
    return []


def normalize_rule_decision(value: str) -> str:
    v = (value or "QUERY").strip().upper()
    return v if v in {"APPROVE", "QUERY", "REJECT"} else "QUERY"


def normalize_severity(value: str) -> str:
    v = (value or "SOFT_QUERY").strip().upper()
    return v if v in {"INFO", "SOFT_QUERY", "HARD_REJECT"} else "SOFT_QUERY"


def medicine_key(name: str) -> str:
    return re.sub(r"\\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(name or "").lower())).strip()

