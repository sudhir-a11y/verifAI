#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import psycopg


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def norm_token(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--doctor", required=True, help="Doctor username/token (e.g. draanchal)")
    args = parser.parse_args()
    doctor_raw = str(args.doctor or "").strip()
    doctor_token = norm_token(doctor_raw)
    if not doctor_token:
        raise SystemExit("doctor token is empty")

    env = load_env(Path(".env"))
    conn = psycopg.connect(
        host=env.get("PG_HOST", "127.0.0.1"),
        port=int(env.get("PG_PORT", "5432")),
        user=env.get("PG_USER", "postgres"),
        password=env.get("PG_PASSWORD", ""),
        dbname=env.get("PG_DATABASE", "qc_bkp_modern"),
    )

    out: dict[str, object] = {"doctor_input": doctor_raw, "doctor_token": doctor_token}
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, username, role
            FROM users
            WHERE LOWER(username) LIKE %s
               OR LOWER(username) LIKE %s
            ORDER BY username
            """,
            (f"%{doctor_raw.lower()}%", "%aanchal%"),
        )
        out["users_matching"] = cur.fetchall()

        cur.execute(
            """
            WITH doc_stats AS (
                SELECT claim_id, COUNT(*) AS documents
                FROM claim_documents
                GROUP BY claim_id
            ),
            latest_assignment AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    occurred_at AS assigned_at,
                    DATE(occurred_at) AS allotment_date
                FROM workflow_events
                WHERE event_type = 'claim_assigned'
                ORDER BY claim_id, occurred_at DESC
            ),
            open_rows AS (
                SELECT
                    c.id,
                    c.external_claim_id,
                    c.status,
                    c.assigned_doctor_id,
                    COALESCE(NULLIF(TRIM(um.tagging), ''), '') AS tagging,
                    COALESCE(NULLIF(TRIM(um.subtagging), ''), '') AS subtagging,
                    CASE WHEN NULLIF(TRIM(COALESCE(um.opinion, '')), '') IS NOT NULL THEN 'yes' ELSE 'no' END AS has_opinion,
                    COALESCE(um.report_export_status, '') AS report_export_status,
                    COALESCE(ds.documents, 0) AS documents,
                    la.assigned_at,
                    la.allotment_date,
                    c.updated_at
                FROM claims c
                LEFT JOIN claim_report_uploads um ON um.claim_id = c.id
                LEFT JOIN doc_stats ds ON ds.claim_id = c.id
                LEFT JOIN latest_assignment la ON la.claim_id = c.id
                WHERE %s = ANY(string_to_array(regexp_replace(LOWER(COALESCE(c.assigned_doctor_id, '')), '[^a-z0-9,]+', '', 'g'), ','))
                  AND c.status <> 'completed'
                  AND c.status <> 'withdrawn'
                  AND NULLIF(TRIM(COALESCE(um.tagging, '')), '') IS NULL
            )
            SELECT
                o.id,
                o.external_claim_id,
                o.status,
                o.assigned_doctor_id,
                o.tagging,
                o.subtagging,
                o.has_opinion,
                o.report_export_status,
                o.documents,
                o.assigned_at,
                o.allotment_date,
                o.updated_at,
                (
                    SELECT we.occurred_at
                    FROM workflow_events we
                    WHERE we.claim_id = o.id
                      AND we.event_type = 'claim_status_updated'
                      AND COALESCE(we.event_payload->>'status', '') = 'completed'
                    ORDER BY we.occurred_at DESC
                    LIMIT 1
                ) AS last_completed_event_at,
                (
                    SELECT MIN(we.occurred_at)
                    FROM workflow_events we
                    WHERE we.claim_id = o.id
                      AND we.event_type = 'claim_status_updated'
                      AND COALESCE(we.event_payload->>'status', '') = 'completed'
                ) AS first_completed_event_at
            FROM open_rows o
            ORDER BY COALESCE(o.allotment_date, DATE(o.updated_at)) ASC, o.updated_at ASC
            """,
            (doctor_token,),
        )
        rows = cur.fetchall()
        out["open_assigned_cases_count"] = len(rows)
        out["open_assigned_cases"] = rows

        if rows:
            claim_ids = [r[0] for r in rows]
            cur.execute(
                """
                SELECT
                    c.external_claim_id,
                    we.event_type,
                    COALESCE(we.event_payload::text, '') AS payload,
                    we.occurred_at
                FROM workflow_events we
                JOIN claims c ON c.id = we.claim_id
                WHERE we.claim_id = ANY(%s)
                  AND we.event_type IN ('claim_assigned', 'claim_status_updated', 'teamrightworks_case_intake')
                ORDER BY c.external_claim_id, we.occurred_at DESC
                """,
                (claim_ids,),
            )
            out["events_for_open_claims"] = cur.fetchall()

    print(json.dumps(out, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
