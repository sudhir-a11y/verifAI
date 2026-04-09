#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import psycopg


TARGET_DATES = [
    "2026-02-16",
    "2026-02-17",
    "2026-02-18",
    "2026-02-20",
    "2026-02-25",
    "2026-02-26",
]


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def main() -> int:
    env = load_env(Path(".env"))
    conn = psycopg.connect(
        host=env.get("PG_HOST", "127.0.0.1"),
        port=int(env.get("PG_PORT", "5432")),
        user=env.get("PG_USER", "postgres"),
        password=env.get("PG_PASSWORD", ""),
        dbname=env.get("PG_DATABASE", "qc_bkp_modern"),
    )

    out: dict[str, object] = {"target_dates": TARGET_DATES}

    with conn, conn.cursor() as cur:
        # Current endpoint logic count (can be inflated if claim_legacy_data has duplicates per claim)
        cur.execute(
            """
            WITH latest_assignment AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    DATE(occurred_at) AS allotment_date
                FROM workflow_events
                WHERE event_type = 'claim_assigned'
                ORDER BY claim_id, occurred_at DESC
            ),
            latest_report AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    export_uri
                FROM report_versions
                ORDER BY claim_id, version_no DESC
            ),
            doctor_saved_reports AS (
                SELECT claim_id, 1 AS has_doctor_saved
                FROM report_versions
                WHERE NULLIF(TRIM(COALESCE(report_markdown, '')), '') IS NOT NULL
                GROUP BY claim_id
            ),
            upload_meta AS (
                SELECT claim_id, report_export_status, tagging, subtagging, opinion
                FROM claim_report_uploads
            ),
            legacy_data AS (
                SELECT claim_id, legacy_payload, updated_at AS legacy_updated_at
                FROM claim_legacy_data
            ),
            base AS (
                SELECT
                    ldata.claim_id,
                    COALESCE(c.external_claim_id, '') AS external_claim_id,
                    COALESCE(
                        CASE
                            WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{4}-\\d{2}-\\d{2}$'
                                THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD')
                            WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{4}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}:\\d{2}$'
                                THEN TO_TIMESTAMP(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD HH24:MI:SS')::date
                            WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}-\\d{2}-\\d{4}$'
                                THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD-MM-YYYY')
                            WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}/\\d{2}/\\d{4}$'
                                THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD/MM/YYYY')
                            ELSE NULL
                        END,
                        DATE(ldata.legacy_updated_at),
                        la.allotment_date,
                        DATE(c.updated_at)
                    ) AS allotment_date,
                    LOWER(TRIM(COALESCE(CAST(c.status AS TEXT), ''))) AS claim_status,
                    CASE
                        WHEN NULLIF(TRIM(COALESCE(um.tagging, '')), '') IS NOT NULL
                          OR NULLIF(TRIM(COALESCE(um.subtagging, '')), '') IS NOT NULL
                          OR NULLIF(TRIM(COALESCE(um.opinion, '')), '') IS NOT NULL
                          OR LOWER(TRIM(COALESCE(um.report_export_status, 'pending'))) = 'uploaded'
                          OR COALESCE(rv.export_uri, '') <> ''
                        THEN 1 ELSE 0
                    END AS is_uploaded,
                    CASE WHEN NULLIF(TRIM(COALESCE(c.assigned_doctor_id, '')), '') IS NOT NULL THEN 1 ELSE 0 END AS is_allotted_to_doctor,
                    CASE WHEN COALESCE(dsr.has_doctor_saved, 0) = 1 THEN 1 ELSE 0 END AS has_doctor_saved
                FROM legacy_data ldata
                LEFT JOIN claims c ON c.id = ldata.claim_id
                LEFT JOIN latest_assignment la ON la.claim_id = ldata.claim_id
                LEFT JOIN upload_meta um ON um.claim_id = ldata.claim_id
                LEFT JOIN latest_report rv ON rv.claim_id = ldata.claim_id
                LEFT JOIN doctor_saved_reports dsr ON dsr.claim_id = ldata.claim_id
            )
            SELECT
                allotment_date::text AS allotment_date,
                COUNT(*) AS rows_seen_by_endpoint,
                COUNT(DISTINCT claim_id) AS distinct_claim_ids,
                COUNT(DISTINCT external_claim_id) AS distinct_external_ids,
                COUNT(*) - COUNT(DISTINCT claim_id) AS duplicate_rows_over_claim_id
            FROM base
            WHERE allotment_date = ANY(%s::date[])
            GROUP BY allotment_date
            ORDER BY allotment_date
            """,
            (TARGET_DATES,),
        )
        out["endpoint_logic_counts"] = cur.fetchall()

        # Which claim_ids have multiple rows in claim_legacy_data on those dates
        cur.execute(
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
                SELECT claim_id, legacy_payload, updated_at AS legacy_updated_at
                FROM claim_legacy_data
            ),
            base AS (
                SELECT
                    ldata.claim_id,
                    COALESCE(c.external_claim_id, '') AS external_claim_id,
                    COALESCE(
                        CASE
                            WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{4}-\\d{2}-\\d{2}$'
                                THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD')
                            WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{4}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}:\\d{2}$'
                                THEN TO_TIMESTAMP(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD HH24:MI:SS')::date
                            WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}-\\d{2}-\\d{4}$'
                                THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD-MM-YYYY')
                            WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}/\\d{2}/\\d{4}$'
                                THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD/MM/YYYY')
                            ELSE NULL
                        END,
                        DATE(ldata.legacy_updated_at),
                        la.allotment_date,
                        DATE(c.updated_at)
                    ) AS allotment_date
                FROM legacy_data ldata
                LEFT JOIN claims c ON c.id = ldata.claim_id
                LEFT JOIN latest_assignment la ON la.claim_id = ldata.claim_id
            )
            SELECT
                allotment_date::text AS allotment_date,
                external_claim_id,
                claim_id::text AS claim_id,
                COUNT(*) AS row_count_for_claim
            FROM base
            WHERE allotment_date = ANY(%s::date[])
            GROUP BY allotment_date, external_claim_id, claim_id
            HAVING COUNT(*) > 1
            ORDER BY allotment_date, row_count_for_claim DESC, external_claim_id
            LIMIT 500
            """,
            (TARGET_DATES,),
        )
        out["duplicate_claim_rows"] = cur.fetchall()

        # Direct duplication in claim_legacy_data table
        cur.execute(
            """
            SELECT claim_id::text AS claim_id, COUNT(*) AS legacy_rows
            FROM claim_legacy_data
            GROUP BY claim_id
            HAVING COUNT(*) > 1
            ORDER BY legacy_rows DESC, claim_id
            LIMIT 200
            """
        )
        out["claim_legacy_data_multi_rows"] = cur.fetchall()

    print(json.dumps(out, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
