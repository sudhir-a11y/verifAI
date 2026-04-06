from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def list_day_wise_completed_current_month(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            WITH latest_assignment AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    DATE(occurred_at) AS allotment_date
                FROM workflow_events
                WHERE event_type = 'claim_assigned'
                ORDER BY claim_id, occurred_at DESC
            ),
            legacy_data AS (
                SELECT claim_id, legacy_payload
                FROM claim_legacy_data
            ),
            completed_base AS (
                SELECT
                    c.status,
                    COALESCE(
                        la.allotment_date,
                        CASE
                            WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\d{4}-\d{2}-\d{2}$'
                                THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD')
                            WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\d{2}-\d{2}-\d{4}$'
                                THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD-MM-YYYY')
                            WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\d{2}/\d{2}/\d{4}$'
                                THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD/MM/YYYY')
                            ELSE NULL
                        END,
                        DATE(c.updated_at)
                    ) AS allotment_date
                FROM claims c
                LEFT JOIN latest_assignment la ON la.claim_id = c.id
                LEFT JOIN legacy_data ldata ON ldata.claim_id = c.id
            )
            SELECT
                cb.allotment_date AS completed_date,
                COUNT(*) AS completed_count
            FROM completed_base cb
            WHERE cb.status = 'completed'
              AND cb.allotment_date >= DATE_TRUNC('month', CURRENT_DATE)::date
              AND cb.allotment_date < (DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month')::date
            GROUP BY cb.allotment_date
            ORDER BY cb.allotment_date DESC
            LIMIT 60
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def list_assignee_wise_stats(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            WITH claim_assignees AS (
                SELECT
                    c.id AS claim_id,
                    c.status,
                    assignee AS assignee_key
                FROM claims c
                CROSS JOIN LATERAL unnest(
                    string_to_array(
                        LOWER(REPLACE(COALESCE(c.assigned_doctor_id, ''), ' ', '')),
                        ','
                    )
                ) AS assignee
                WHERE NULLIF(TRIM(COALESCE(c.assigned_doctor_id, '')), '') IS NOT NULL
                  AND NULLIF(TRIM(assignee), '') IS NOT NULL
            ),
            assignee_stats AS (
                SELECT
                    ca.assignee_key,
                    COUNT(*) FILTER (WHERE ca.status = 'completed') AS completed_count,
                    COUNT(*) FILTER (WHERE ca.status NOT IN ('completed', 'withdrawn')) AS pending_count
                FROM claim_assignees ca
                GROUP BY ca.assignee_key
            )
            SELECT
                COALESCE(u.username, s.assignee_key) AS username,
                COALESCE(CAST(u.role AS TEXT), '') AS role,
                CAST(s.completed_count AS INTEGER) AS completed_count,
                CAST(s.pending_count AS INTEGER) AS pending_count,
                CAST(s.completed_count + s.pending_count AS INTEGER) AS total_count
            FROM assignee_stats s
            LEFT JOIN users u
                ON LOWER(u.username) = s.assignee_key
            ORDER BY (s.completed_count + s.pending_count) DESC, COALESCE(u.username, s.assignee_key) ASC
            LIMIT 500
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]

