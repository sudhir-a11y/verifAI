#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    path = Path("/home/ec2-user/qc-python/app/api/v1/endpoints/user_tools.py")
    text = path.read_text(encoding="utf-8")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(path.name + f".bak_{ts}")
    backup.write_text(text, encoding="utf-8")

    old1 = """                COUNT(*) FILTER (
                    WHERE b.is_allotted_to_doctor = 1
                      AND b.has_doctor_saved = 0
                      AND NOT (b.claim_status = 'completed' AND b.is_uploaded = 1)
                ) AS pending_count,"""
    new1 = """                COUNT(*) FILTER (
                    WHERE NOT (b.claim_status = 'completed' AND b.is_uploaded = 1)
                ) AS pending_count,"""

    old2 = """    elif normalized_bucket == "pending":
        filters.append(
            "b.is_allotted_to_doctor = 1 AND b.has_doctor_saved = 0 "
            "AND NOT (b.claim_status = 'completed' AND b.is_uploaded = 1)"
        )"""
    new2 = """    elif normalized_bucket == "pending":
        filters.append("NOT (b.claim_status = 'completed' AND b.is_uploaded = 1)")"""

    old3 = """                    WHEN b.claim_status = 'completed' AND b.is_uploaded = 1 THEN 'completed'
                    WHEN b.is_allotted_to_doctor = 1
                      AND b.has_doctor_saved = 0
                      AND NOT (b.claim_status = 'completed' AND b.is_uploaded = 1)
                    THEN 'pending'"""
    new3 = """                    WHEN b.claim_status = 'completed' AND b.is_uploaded = 1 THEN 'completed'
                    WHEN NOT (b.claim_status = 'completed' AND b.is_uploaded = 1) THEN 'pending'"""

    for old, new in ((old1, new1), (old2, new2), (old3, new3)):
        if old not in text:
            raise SystemExit("Expected pattern not found; aborting patch.")
        text = text.replace(old, new, 1)

    path.write_text(text, encoding="utf-8")
    print(str(backup))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
