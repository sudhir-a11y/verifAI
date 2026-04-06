from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def list_month_wise_closed(db: Session, *, doctor_key: str) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            WITH completed_claims AS (
                SELECT
                    c.id,
                    DATE(COALESCE(c.completed_at, c.updated_at) AT TIME ZONE 'Asia/Kolkata') AS completed_date,
                    COALESCE(c.assigned_doctor_id, '') AS assigned_doctor_id
                FROM claims c
                WHERE c.status = 'completed'
                  AND COALESCE(c.completed_at, c.updated_at) IS NOT NULL
            ),
            scoped_claims AS (
                SELECT
                    cc.id,
                    cc.completed_date
                FROM completed_claims cc
                WHERE :doctor_key = ''
                   OR EXISTS (
                        SELECT 1
                        FROM unnest(
                            string_to_array(
                                regexp_replace(LOWER(cc.assigned_doctor_id), '[^a-z0-9,]+', '', 'g'),
                                ','
                            )
                        ) AS token
                        WHERE NULLIF(token, '') IS NOT NULL
                          AND token = :doctor_key
                   )
            )
            SELECT
                DATE_TRUNC('month', sc.completed_date)::date AS month_start,
                TO_CHAR(DATE_TRUNC('month', sc.completed_date), 'YYYY-MM') AS month_key,
                TO_CHAR(DATE_TRUNC('month', sc.completed_date), 'Mon YYYY') AS month_label,
                COUNT(*)::integer AS closed_count
            FROM scoped_claims sc
            GROUP BY DATE_TRUNC('month', sc.completed_date)
            ORDER BY DATE_TRUNC('month', sc.completed_date) DESC
            LIMIT 36
            """
        ),
        {"doctor_key": doctor_key},
    ).mappings().all()
    return [dict(r) for r in rows]


def list_day_wise_closed(
    db: Session,
    *,
    doctor_key: str,
    month_start: date,
) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            WITH completed_claims AS (
                SELECT
                    c.id,
                    DATE(COALESCE(c.completed_at, c.updated_at) AT TIME ZONE 'Asia/Kolkata') AS completed_date,
                    COALESCE(c.assigned_doctor_id, '') AS assigned_doctor_id
                FROM claims c
                WHERE c.status = 'completed'
                  AND COALESCE(c.completed_at, c.updated_at) IS NOT NULL
            ),
            scoped_claims AS (
                SELECT
                    cc.id,
                    cc.completed_date
                FROM completed_claims cc
                WHERE :doctor_key = ''
                   OR EXISTS (
                        SELECT 1
                        FROM unnest(
                            string_to_array(
                                regexp_replace(LOWER(cc.assigned_doctor_id), '[^a-z0-9,]+', '', 'g'),
                                ','
                            )
                        ) AS token
                        WHERE NULLIF(token, '') IS NOT NULL
                          AND token = :doctor_key
                   )
            )
            SELECT
                sc.completed_date AS completed_date,
                COUNT(*)::integer AS closed_count
            FROM scoped_claims sc
            WHERE sc.completed_date >= :month_start
              AND sc.completed_date < (:month_start + INTERVAL '1 month')::date
            GROUP BY sc.completed_date
            ORDER BY sc.completed_date DESC
            """
        ),
        {"doctor_key": doctor_key, "month_start": month_start},
    ).mappings().all()
    return [dict(r) for r in rows]


__all__ = ["list_day_wise_closed", "list_month_wise_closed"]

